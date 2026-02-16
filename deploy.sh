#!/bin/bash

set -e

PROJECT_ID="shopq-467118"
REGION="us-central1"
SERVICE_NAME="reclaim-api"

echo "🚀 Deploying Reclaim API to Cloud Run..."

# Set project
gcloud config set project $PROJECT_ID

# Get project number
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

echo "📋 Granting permissions to Cloud Build service account..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/storage.admin" \
  --quiet

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/run.admin" \
  --quiet

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser" \
  --quiet

echo "⏳ Waiting for permissions to propagate..."
sleep 30

echo "🏗️  Building and deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --source . \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$PROJECT_ID,\
GOOGLE_API_KEY=${GOOGLE_API_KEY},\
GOOGLE_OAUTH_CLIENT_ID=${GOOGLE_OAUTH_CLIENT_ID},\
RECLAIM_EXTENSION_IDS=${RECLAIM_EXTENSION_IDS},\
GEMINI_MODEL=gemini-2.0-flash,\
GEMINI_LOCATION=us-central1,\
RECLAIM_ENV=production \
  --memory 512Mi \
  --timeout 300s \
  --cpu 1 \
  --concurrency 10

echo "✅ Deployment complete!"
echo ""
echo "🌐 Getting service URL..."
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)')
echo "📍 Your API is deployed at: $SERVICE_URL"
echo ""
echo "🧪 Testing health endpoint..."
curl -s "$SERVICE_URL/health" | jq .
echo ""
echo "⚙️  Update your extension config with:"
echo "  API_BASE_URL: '$SERVICE_URL'"
