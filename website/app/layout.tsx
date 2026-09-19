import type { Metadata } from 'next';
import '@fontsource-variable/inter';
import './globals.css';

const siteUrl = 'https://geotrace-ai-forensics.riteshbhardwaj364.chatgpt.site';

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: 'GeoTrace AI — Trace what images don’t say',
  description: 'AI-assisted image geolocation and digital forensics. Explore the evidence behind an image.',
  icons: { icon: '/favicon.svg' },
  openGraph: {
    type: 'website',
    url: '/',
    siteName: 'GeoTrace AI',
    title: 'GeoTrace AI — Trace what images don’t say',
    description: 'AI-assisted image geolocation and digital forensics with transparent evidence analysis.',
    images: [{ url: '/og.png', width: 1200, height: 630, alt: 'GeoTrace AI — Trace what images don’t say' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'GeoTrace AI — Trace what images don’t say',
    description: 'AI-assisted image geolocation and digital forensics with transparent evidence analysis.',
    images: ['/og.png'],
  },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
