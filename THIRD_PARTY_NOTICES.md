# Third-party assets and software

GhostRep source code is distributed under the MIT license in LICENSE. Third-party software and assets retain their applicable licenses.

## Fonts

The app uses Sora, Syne, and IBM Plex Mono through next/font/google. Their SIL Open Font License 1.1 notices are redistributed in docs/licenses/sora-OFL.txt, syne-OFL.txt, and ibmplexmono-OFL.txt. Unmodified notices were fetched from the official google/fonts repository on October 31, 2026. Preserve them when distributing self-hosted font bundles. Sources: https://github.com/google/fonts/tree/main/ofl/sora ; https://github.com/google/fonts/tree/main/ofl/syne ; https://github.com/google/fonts/tree/main/ofl/ibmplexmono .

## Source dependencies

Exact versions are pinned by frontend/package-lock.json and backend/uv.lock. Frontend runtime libraries include Next.js, React, react-dom, lucide-react, Recharts, react-hook-form, Zod, clsx, and tailwind-merge. Backend libraries include FastAPI, SQLAlchemy, Pydantic, NumPy, SciPy, OpenCV, MediaPipe, HTTPX, OpenAI's SDK, and meta-sam-parser. Their package distributions include their own license notices; retain those when distributing installed dependencies. This source snapshot does not vendor dependencies or claim ownership of them.

FFmpeg/FFprobe are external prerequisites; licensing depends on the installed build and enabled codecs. The repository does not redistribute those binaries. The MediaPipe pose model downloads separately from Google's model host; it is not included in the source snapshot. Review Google's applicable model terms for a hosted distribution.

## Project graphics and fixtures

frontend/public contains the GhostRep brand SVGs, derived app icons, and the recorded squat example supplied by the project owner for this application. The recorded example is distinct from the synthetic journal and is not a standard of ideal technique. Source licensing does not override third-party image, footage, likeness, or trademark rights.

fixtures/meta contains illustrative JSON, not private athlete video or a claim that every fixture is a real model result. Other local recordings, athlete databases, downloaded models, and developer inference artifacts are excluded from source export. The submission video is a separate artifact and is not bundled as application source.
