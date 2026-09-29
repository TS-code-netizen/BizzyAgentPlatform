import { writeFileSync } from 'node:fs'

writeFileSync('dist/release.json', JSON.stringify({
  frontend_commit: process.env.GITHUB_SHA,
  backend_commit: process.env.BACKEND_COMMIT,
  dataset_commit: process.env.DATASET_COMMIT,
  model_id: process.env.BEDROCK_MODEL_ID || 'disabled',
  api_base_url: process.env.VITE_API_BASE_URL,
}, null, 2))
