# RibhLab RealMotion — Cloud Setup (GitHub + Vercel + AI)

## What this architecture does

- GitHub holds **only code**; GitHub Pages can host the static page.
- Vercel hosts the same web page **plus authenticated API routes**. No server or NVIDIA card is required for visitors.
- Replicate performs **actual AI video and TTS processing on hosted GPU**. Video generation is usage-billed. GitHub has no built-in video GPU.
- Images stay in the browser until the owner starts generation. Uploads go directly from the authorized visitor's browser via Vercel to the AI provider. **Never commit children's photographs or access credentials to GitHub**.

## One-time administrator setup

1. Open https://vercel.com/new and import `ribhlab/RibhLab-RealMotion`. Select the repository root and deploy as **Other / No framework**. Or create a Git-linked project from the API. No custom build command required.
2. In Vercel project **Settings → Environment Variables**, add `REPLICATE_API_TOKEN` with a token created directly at https://replicate.com/account/api-tokens. Use **Sensitive** (or encrypted) type and apply to production. Do not send the token through chat. A token alone is insufficient unless the Replicate account has generation credit.
3. Add `REALMOTION_ACCESS_PIN`: a long random value of **12 or more characters** that only authorized family members know. This PIN is not a provider token; it unlocks your limited cloud GPU account. Use sensitive type; apply to production. Consider a provider spend cap and restricted access if publishing the site widely.
4. (Optional) Set `REALMOTION_ALLOWED_ORIGINS=https://ribhlab.github.io` if using a GitHub Pages mirror. The GitHub Pages mirror should set `window.REALMOTION_API_BASE` to your Vercel production URL in a *public config only*. Don't put credentials there.
5. Redeploy production after the environment variables are saved.
6. Visit your deployment, check that the status reads **محرك AI متصل**. Upload four photos, enter the owner's access code, and press **أنتج الفيلم**. The browser asks for approval before making any charged model requests. The cloud generates 6 clips, then the browser assembles the final movie.

**Do not use GitHub Actions secrets to upload photos to a public GitHub repository or create public issues containing children's photos.** This architecture avoids that.

## Supported cloud models

| Purpose | Replicate model | Contract |
| --- | --- | --- |
| Motion & driving | `wan-video/wan-2.2-5b-fast` | Image, prompt, 121 frames @ 24fps, portrait ratio |
| Synthetic Arabic voice (not cloned) | `resemble-ai/chatterbox-multilingual` | Text, language `ar`, default generic voice |
| Audio-driven speaking | `wan-video/wan-2.2-s2v` | Image, audio URL, prompt |

Official schemas: https://replicate.com/wan-video/wan-2.2-5b-fast/api/schema , https://replicate.com/wan-video/wan-2.2-s2v/api/schema , https://replicate.com/resemble-ai/chatterbox-multilingual/api/schema

Models may change upstream. Audio quality in Moroccan dialect is not guaranteed. Group scenes derived from a 2×2 collage cannot guarantee four identical real faces; use appropriate reference composition if needed.

## Backend API

- `GET /api/config`: service status, no secrets.
- `POST /api/start`: authenticated by header `x-realmotion-pin`; accepts one predefined mode (motion, voice, talk). No arbitrary model name is accepted.
- `GET /api/status?id=...`: authenticates then reads a Replicate prediction status.
- `GET /api/media?url=...`: authenticated media proxy; only generated Replicate delivery hostnames allowed. Browser first attempts a direct CORS download, then proxy fallback.

### Cloud limitations

- 4.5MB platform request/response limits apply to some Vercel plans. The browser compresses each image to a small JPEG before submission.
- The browser orchestrates the six AI jobs sequentially; closing/reloading it may interrupt the unfinished storyboard even though already requested GPU predictions may continue.
- A shared access PIN is a minimal initial gate, not production-grade accounts, quotas or abuse protection. For public commercial use add login, per-user budget, persistent jobs, billing controls, moderation and private object storage.
- Replicate inference is not free by default. **No provider API key is included in this repo**, and a GitHub/Vercel deploy alone does not make actual rendering possible.
- A movie can take more than several minutes to render. Download individual clips if the browser cannot combine them.
