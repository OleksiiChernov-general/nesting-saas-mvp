# Quick Deployment Guide - Nesting SaaS MVP

## Pre-Deployment Verification

Before deploying to Railway, verify the local changes:

```bash
# Backend - verify no syntax errors
cd nesting_saas_mvp
python -m py_compile app/nesting.py app/schemas.py app/api.py

# Frontend - check TypeScript compilation
cd frontend
npm run build 2>&1 | head -20
```

## Deployment Steps

1. **Commit Changes**
```bash
git add .
git commit -m "feat: implement production nesting workflow with fill_sheet and batch_quantity modes"
```

2. **Push to Railway Branch**
```bash
git push origin main  # or your configured Railway branch
```

3. **Railway Auto-Deploy**
- Railway will automatically detect changes
- Backend will rebuild Docker image for `nesting_saas_mvp`
- Frontend will rebuild Docker image for `deploy_frontend_temp`
- Deployment typically takes 3-5 minutes

## Post-Deployment Verification

### Health Check
```bash
# Replace with actual Railway domain
curl https://your-nesting-api.railway.app/health
# Expected: {"status": "ok"}
```

### Frontend Manual Test
1. Open https://your-nesting-web.railway.app
2. Look for "Fill Sheet" and "Batch Quantity" buttons in the Nesting Job panel
3. Verify buttons are clickable and change appearance on selection

### API Test
```bash
# Get available endpoints
curl https://your-nesting-api.railway.app/docs

# Test file import (requires DXF file)
curl -X POST \
  -F "file=@sample.dxf" \
  https://your-nesting-api.railway.app/v1/files/import

# Test nesting job creation
curl -X POST -H "Content-Type: application/json" \
  -d '{
    "mode": "fill_sheet",
    "parts": [{"part_id": "p1", "quantity": 1, "polygon": {"points": [{"x":0,"y":0},{"x":10,"y":0},{"x":10,"y":10},{"x":0,"y":10},{"x":0,"y":0}]}}],
    "sheets": [{"sheet_id": "s1", "width": 100, "height": 100, "quantity": 1}],
    "params": {"gap": 0, "rotation": [0,180]}
  }' \
  https://your-nesting-api.railway.app/v1/nesting/jobs
```

## Troubleshooting

### Frontend Not Updating
- Chrome: Ctrl+Shift+R (hard refresh)
- Safari: Cmd+Shift+R or Settings > Develop > Empty Caches
- Check Network tab for new JavaScript files

### Backend 500 Errors
- Check Railway logs for backend service
- Common issues:
  - Missing environment variables
  - Database connection issues
  - Missing dependencies

### Nesting Still Places Few Parts
- Verify algorithm file changed: `grep "grid_spacing" app/nesting.py`
- Check Docker image rebuild completed
- Try a simple test case: 100x100 sheet, 10x10 part, fill_sheet mode

## Rollback (if needed)

```bash
# If previous version is still in Railway services:
# 1. Go to Railway dashboard
# 2. Select service, go to Deployments
# 3. Click on previous version
# 4. Click "Redeploy"

# Or via git:
git revert HEAD
git push origin main
```

## Environment Variables

Ensure Railway has these set (usually from Railway template):
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `CORS_ALLOWED_ORIGIN`: Frontend URL for CORS

## Support

For deployment issues:
1. Check Railway service logs
2. Verify environment variables are set
3. Check git push completed successfully
4. Review local changes with `git diff HEAD~1`

---

**Last Updated**: March 27, 2026
**Tested Platforms**: Windows, Linux, macOS