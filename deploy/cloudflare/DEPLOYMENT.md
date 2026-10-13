# Current Cloudflare deployment

Frontend URL: https://dataneat.dataneat-9df71239.workers.dev

Published on 2026-10-13 from application commit `4276967`.
Worker: `dataneat`
Cloudflare version: `aa96e35d-085f-4cf6-976b-3304e34bd8e0`

Wrangler completed asset upload and deployment. Cloudflare's API confirmed that workers.dev publication and preview URLs are enabled. The static build passed before publication.

**Frontend only:** `BACKEND_ORIGIN` is not configured. The website can be viewed, but spreadsheet uploads, cleaning, and downloads require a hosted Python backend. The Worker returns an explicit HTTP 503 for API calls until that server is connected. This deployment must not be presented as a fully operational cleaning service.

Direct HTTPS page verification from the Codex environment was blocked by its outbound host policy. This is distinct from the successful Cloudflare publication and is not evidence that the public URL is unavailable to browsers.

No API token is stored in this repository. Future publication uses the securely configured CLOUDFLARE_API_TOKEN and the existing deployment configuration.
