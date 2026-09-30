# Instagram and social-post geolocation methods

Updated: 2026-09-30

No method can locate every Instagram post. Private or deleted posts, login
walls, reposted media, stripped metadata, altered or generated imagery, false
location tags, indoor scenes, and visually generic content can make a reliable
location unknowable.

## Evidence supported by research

1. Fuse the post image with caption and hashtag text. Multimodal Instagram
   location research reports stronger inference than single-modality methods.
2. Predict at geographic hierarchies rather than forcing a single exact point.
   Scene-aware country/state/city representations improve worldwide visual
   geolocation.
3. Extract scene text. Business names, road signs, and addresses can be strong
   retrieval clues, though natural-scene OCR is difficult under blur,
   perspective, compression, and unusual typography.
4. Retrieve against a geotagged image gallery. Street- or landmark-level
   localization depends on reference coverage and robust image retrieval.
5. Treat social-media tags as claims requiring corroboration. Image and text
   may intentionally refer to different places or meanings.

## Implemented in GeoTrace

- Public Open Graph/Twitter preview collection with recorded provenance.
- Operator-provided caption, hashtags, displayed location, capture time, and
  account reference.
- On-device OCR and Indian-script detection.
- GeoCLIP regional visual candidates.
- A local GeoNames India index with roughly 660,000 features and 1.06 million
  names/aliases.
- Text, OCR, EXIF, and visual candidates retained as distinct evidence and
  clustered geographically.
- Evidence-coverage assessment that does not claim calibrated confidence.

## Sources

- https://arxiv.org/abs/2306.07935
- https://aclanthology.org/D19-1469/
- https://openaccess.thecvf.com/content/CVPR2023/html/Clark_Where_We_Are_and_What_Were_Looking_At_Query_Based_CVPR_2023_paper.html
- https://openaccess.thecvf.com/content/CVPR2020/html/Weyand_Google_Landmarks_Dataset_v2_-_A_Large-Scale_Benchmark_for_Instance-Level_CVPR_2020_paper.html
- https://openaccess.thecvf.com/content_cvpr_2016/papers/Shi_Robust_Scene_Text_CVPR_2016_paper.pdf
- https://www.geonames.org/export/
