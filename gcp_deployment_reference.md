# GOOGLE CLOUD DEPLOYMENT CONTEXT (STRICT)
# Date: January 2026
# Target Stack: Python 3.14+, FastAPI, Cloud Run, Firestore

## 1. CORE PHILOSOPHY
- **Compute:** default to **Cloud Run** (Services or Jobs). Do NOT use App Engine or Cloud Functions Gen 1.
- **Functions:** If "Functions" are requested, use **Cloud Run functions** (Gen 2).
- **Registry:** STRICTLY use **Artifact Registry** (`pkg.dev`). `gcr.io` is deprecated/shutdown.
- **Identity:** Use **Workload Identity Federation** (WIF) for CI/CD. NEVER generate JSON Service Account keys.

## 2. INFRASTRUCTURE SPECIFICS

### A. Python 3.14 Runtime
- **Buildpacks:** Google Buildpacks for Python 3.14+ now default to using **`uv`** for dependency resolution.
- **Base Image:** `python:3.14-slim` is the preferred Docker base.
- **Dockerfile Pattern:**
  FROM python:3.14-slim
  COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
  ENV PATH="/app/.venv/bin:$PATH"
  WORKDIR /app
  COPY pyproject.toml .
  RUN uv sync --frozen
  COPY . .
  CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]

### B. Cloud Run (Services)
- **Deploy Command:**
  gcloud run deploy service-name \
    --image LOCATION-docker.pkg.dev/PROJECT_ID/REPO/IMAGE:TAG \
    --region us-central1 \
    --allow-unauthenticated \
    --memory 512Mi --cpu 1
- **Networking:** Use **Direct VPC Egress** (not Serverless VPC Access Connectors) for database connections.
  `--vpc-egress=private-ranges-only --network=default`
- **Secrets:** Mount secrets as volumes for files, or env vars for strings.
  `--set-secrets="/secrets/api_key=my-secret:latest"`

### C. Cloud Run functions (Gen 2)
- **Naming:** Refer to them as "Cloud Run functions".
- **Deploy Command:**
  gcloud functions deploy my-function \
    --gen2 \
    --runtime=python314 \
    --region=us-central1 \
    --source=. \
    --entry-point=main \
    --trigger-http

### D. Artifact Registry
- **Format:** `LOCATION-docker.pkg.dev/PROJECT-ID/REPOSITORY-ID/IMAGE:TAG`
- **Creation:**
  gcloud artifacts repositories create my-repo \
    --repository-format=docker \
    --location=us-central1

### E. Firestore (Native Mode)
- **Database Creation:**
  gcloud firestore databases create \
    --region=us-central1 \
    --type=firestore-native
- **Connection:** Use `google-cloud-firestore` Python client library
- **IAM Role:** `roles/datastore.user` for read/write access

## 3. FIRESTORE POI SUBCOLLECTIONS

### A. POI Storage Architecture
- **Storage Model:** POIs are stored in per-character subcollections at `characters/{character_id}/pois/{poi_id}`
- **Deprecated:** Embedded `world_pois` arrays in character documents (read-only during migration)
- **Benefits:** Unlimited storage, efficient pagination, Firestore best practices

### B. Required Firestore Indexes
**Automatic Index Creation:**
Firestore automatically creates composite indexes when queries are first executed. The following indexes are created for POI subcollections:

1. **Timestamp Ordering (auto-created):**
   - Collection: `pois` (subcollection)
   - Field: `timestamp_discovered` (descending)
   - Query scope: Collection group
   - Used by: `GET /characters/{id}/pois` with pagination

2. **Count Aggregation:**
   - No additional index required
   - Uses built-in Firestore count aggregation
   - Used by: `GET /characters/{id}/pois/summary`

**Verify Indexes:**
```bash
gcloud firestore indexes composite list --project=PROJECT_ID
# Expected: pois collection with timestamp_discovered (DESCENDING)
```

**Manual Index Creation (if auto-creation disabled):**
```bash
gcloud firestore indexes composite create \
  --collection-group=pois \
  --field-config field-path=timestamp_discovered,order=descending \
  --project=PROJECT_ID
```

### C. Firestore Quota Considerations

**POI Subcollection Query Costs:**
- **Read operations:** Each POI document read counts as 1 read
- **Count aggregation:** Approximately 1/1000th the cost of reading all documents
- **Pagination:** Cursor-based pagination reuses query results, efficient for large collections

**Expected Query Patterns:**
| Endpoint | Firestore Reads | Notes |
|----------|-----------------|-------|
| `GET /pois?limit=20` | 21 reads | Fetches limit+1 to determine next page |
| `GET /pois/summary` | ~1 read | Count aggregation (efficient) |
| `GET /pois/random?n=5` | 1 read + 5 in-memory samples | Reads from parent document embedded array (legacy) or subcollection |
| `POST /pois` | 1 read + 1 write | Verify character + write POI |
| `PUT /pois/{id}` | 1 read + 1 write | Read existing + update |
| `DELETE /pois/{id}` | 1 write | Delete POI document |

**Quota Limits (Firestore Standard Tier):**
- **Free tier:** 50,000 reads/day, 20,000 writes/day
- **Paid tier:** No daily limits, charged per operation
- **Rate limits:** 10,000 writes/second per database

**Recommendations:**
1. **Monitor usage:** Check Firestore usage metrics in GCP Console
2. **Optimize queries:** Use cursor-based pagination instead of offset
3. **Cache counts:** Cache POI summary counts client-side (low change frequency)
4. **Batch operations:** Use transactions for multi-POI operations

### D. Performance Characteristics

**Latency Expectations:**
- **GET /pois with pagination (limit=20):** <100ms for indexed queries
- **GET /pois/summary (count + preview):** <150ms with aggregation
- **POST /pois:** <200ms including validation and write
- **PUT /pois/{id}:** <150ms for single document update
- **DELETE /pois/{id}:** <100ms for single document delete

**Scaling Characteristics:**
- **Character count:** No impact on individual character POI queries (isolated subcollections)
- **POIs per character:** Linear query time with pagination (O(limit) per request)
- **Concurrent queries:** Firestore handles high concurrency (10k+ reads/sec)

**Optimization Tips:**
1. **Use cursor pagination:** Avoid offset-based pagination for large collections
2. **Limit query size:** Default limit=50, max=100 for paginated endpoints
3. **Cache POI counts:** Update count only when POIs change
4. **Use summary endpoint:** For count-only queries, use aggregation instead of fetching all documents

### E. Migration Considerations

**Migration Script:** `scripts/migrate_character_pois.py`

**Firestore Operations During Migration:**
- **Per character:** 1 read (character document) + N writes (POI subcollection documents) + 1 write (remove embedded array)
- **Example:** Character with 50 embedded POIs = 1 read + 50 writes + 1 write = 52 operations
- **Large migration:** 1000 characters × 50 POIs avg = 52,000 operations

**Quota Impact:**
- **Estimate usage:** Run dry-run mode first to calculate total operations
- **Batch processing:** Use `--limit` flag to process in batches
- **Rate limiting:** Script includes delays to avoid quota exhaustion

**Rollout Strategy:**
1. **Staging:** Test with small subset (`--limit 10`)
2. **Production:** Batch process during low-traffic window
3. **Monitor:** Watch Firestore quota usage during migration

### F. Monitoring and Alerting

**Key Metrics to Monitor:**

1. **Firestore Quota Usage:**
   ```bash
   # Navigate to: GCP Console → Firestore → Usage
   # Monitor: Read/write operations, storage size
   ```

2. **API Latency:**
   ```bash
   # Check Cloud Run metrics
   # Expected: P50 <100ms, P95 <200ms for POI endpoints
   ```

3. **Error Rates:**
   ```bash
   # Monitor 429 ResourceExhausted errors (quota exceeded)
   gcloud logging read "severity>=ERROR AND jsonPayload.error_type=ResourceExhausted" \
     --project=PROJECT_ID \
     --limit=10
   ```

**Alerting Rules:**

```yaml
# Example Cloud Monitoring alert policy (YAML format)
displayName: "Firestore POI Query Latency Alert"
conditions:
  - displayName: "Latency > 500ms"
    conditionThreshold:
      filter: |
        resource.type = "cloud_run_revision"
        AND metric.type = "run.googleapis.com/request_latencies"
        AND metric.labels.route = "/characters/*/pois"
      aggregations:
        - alignmentPeriod: 60s
          perSeriesAligner: ALIGN_DELTA
      comparison: COMPARISON_GT
      thresholdValue: 500
      duration: 300s
```

## 4. IAM AND SECURITY

### A. Service Account Permissions

**Required Roles for POI Operations:**
```bash
# Grant Firestore access to Cloud Run service account
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:SERVICE_ACCOUNT@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

**Permissions Breakdown:**
- `datastore.entities.create` - Create POI documents in subcollections
- `datastore.entities.get` - Read character and POI documents
- `datastore.entities.update` - Update POI documents
- `datastore.entities.delete` - Delete POI documents
- `datastore.entities.list` - Query POI subcollections

### B. Firestore Security Rules (Optional)

If using Firestore in Datastore mode or native mode with security rules:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Character access
    match /characters/{characterId} {
      allow read, write: if request.auth != null && 
                            request.auth.uid == resource.data.owner_user_id;
      
      // POI subcollection access
      match /pois/{poiId} {
        allow read: if request.auth != null && 
                       get(/databases/$(database)/documents/characters/$(characterId)).data.owner_user_id == request.auth.uid;
        allow write: if request.auth != null && 
                        get(/databases/$(database)/documents/characters/$(characterId)).data.owner_user_id == request.auth.uid;
      }
    }
  }
}
```

## 5. POSTGRESQL 18 (Cloud SQL) - Not Used in Journey Log

### E. PostgreSQL 18 (Cloud SQL)
- **Connection:** Use `cloud_sql_proxy` (v2) or the Python `cloud-sql-python-connector` library.
- **Async Driver:** `asyncpg` is preferred for FastAPI.

**Note:** Journey Log uses Firestore, not PostgreSQL. The above is reference information for other projects.
