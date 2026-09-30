import unittest
from email.message import Message
from unittest.mock import patch

from social_collection_service import (
    PublicCollectionError,
    collect_public_media,
    validate_public_url,
)


def public_resolver(_host, _port, **_kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def private_resolver(_host, _port, **_kwargs):
    return [(2, 1, 6, "", ("127.0.0.1", 80))]


class FakeResponse:
    def __init__(self, url, content_type, payload):
        self.url = url
        self.payload = payload
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.headers["Content-Length"] = str(len(payload))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.url

    def read(self, limit):
        return self.payload[:limit]


class FakeOpener:
    def open(self, request, timeout):
        if request.full_url.endswith("/no-preview"):
            return FakeResponse(
                request.full_url,
                "text/html; charset=utf-8",
                b'<meta property="og:title" content="Visit New Delhi">'
                b'<meta property="og:description" content="Evening at India Gate">',
            )
        if request.full_url.endswith("/post"):
            return FakeResponse(
                request.full_url,
                "text/html; charset=utf-8",
                b'<meta property="og:title" content="Public post">'
                b'<meta property="og:description" content="Visit #NewDelhi">'
                b'<meta property="og:image" content="/preview.png">',
            )
        return FakeResponse(request.full_url, "image/png", b"png-image-bytes")


class SocialCollectionServiceTests(unittest.TestCase):
    def test_accepts_public_https_url(self):
        value = validate_public_url(
            "https://example.com/public/post", resolver=public_resolver
        )
        self.assertEqual(value, "https://example.com/public/post")

    def test_blocks_private_network_destination(self):
        with self.assertRaises(PublicCollectionError):
            validate_public_url("http://example.test/image", resolver=private_resolver)

    def test_blocks_credentials_in_url(self):
        with self.assertRaises(PublicCollectionError):
            validate_public_url(
                "https://user:password@example.com/post", resolver=public_resolver
            )

    @patch(
        "social_collection_service.validate_public_url",
        side_effect=lambda value: value,
    )
    def test_collects_open_graph_preview(self, _validate):
        result = collect_public_media(
            "https://example.com/post", opener=FakeOpener()
        )

        self.assertEqual(result["data"], b"png-image-bytes")
        self.assertEqual(result["content_type"], "image/png")
        self.assertEqual(result["collection"]["page"]["title"], "Public post")
        self.assertEqual(result["collection"]["page"]["hashtags"], ["#NewDelhi"])
        self.assertEqual(
            result["collection"]["resolved_image_url"],
            "https://example.com/preview.png",
        )

    @patch(
        "social_collection_service.validate_public_url",
        side_effect=lambda value: value,
    )
    def test_keeps_public_page_metadata_without_preview_image(self, _validate):
        result = collect_public_media(
            "https://example.com/no-preview", opener=FakeOpener()
        )

        self.assertEqual(result["data"], b"")
        self.assertEqual(
            result["collection"]["method"], "automatic_public_page_metadata"
        )
        self.assertEqual(
            result["collection"]["page"]["description"],
            "Evening at India Gate",
        )
        self.assertIsNone(result["collection"]["resolved_image_url"])


if __name__ == "__main__":
    unittest.main()
