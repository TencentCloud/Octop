#!/bin/bash
# Medical Imaging Suite Deployment

set -e

MODE="${1:-all}"

echo "🚀 Deploying Medical Imaging Suite..."
echo "📦 Mode: $MODE"

case $MODE in
  all)
    echo "📦 Deploying OHIF Viewer + Segmentation API..."
    # Placeholder for full deployment
    echo "✅ Use ohif-deploy and dicom-segmentation-api skills"
    ;;
  viewer)
    echo "📦 Deploying OHIF Viewer only..."
    echo "✅ Use ohif-deploy skill"
    ;;
  segmentation)
    echo "📦 Deploying Segmentation API only..."
    echo "✅ Use dicom-segmentation-api skill"
    ;;
esac

echo "📚 For full deployment, use individual skills:"
echo "   - ohif-deploy"
echo "   - dicom-segmentation-api"
