import requests
import json
import io

base_url = "http://127.0.0.1:8002"

# 1. Create a LAS file with duplicate curve names in memory
las_content = """~Version Section
VERS.                          2.0 :   CWLS log ASCII Standard -VERSION 2.0
WRAP.                          NO  :   One line per depth step
~Well Section
STRT.M                         10.0 :   START DEPTH
STOP.M                         12.0 :   STOP DEPTH
STEP.M                         1.0  :   STEP
NULL.                          -999.25 :   NULL VALUE
WELL.                          ANY WELL :   WELL NAME
~Curve Information Section
DEPT.M                             :   1  DEPTH
GR  .API                           :   2  GAMMA RAY
GR  .API                           :   3  DUPLICATE GAMMA RAY
~Parameter Information Section
~Ascii Section
10.0 50.0 55.0
11.0 60.0 65.0
12.0 70.0 75.0
"""

files = {
    'file': ('duplicate_curves.las', io.BytesIO(las_content.encode('utf-8')), 'application/octet-stream')
}

upload_url = f"{base_url}/api/v1/preprocess/upload"
r1 = requests.post(upload_url, files=files)
print(f"Upload Status Code: {r1.status_code}")
job_id = None
try:
    upload_res = r1.json()
    job_id = upload_res.get('jobId')
except Exception as e:
    pass

if not job_id:
    print(f"Failed to get job_id. Response: {r1.text}")
    exit(1)

# 2. Call workbench/run
# Based on error, jobId might be needed in body
run_url = f"{base_url}/api/v1/preprocess/workbench/run"
payload = {
    "jobId": job_id,
    "methods": ["las_to_excel"],
    "saveToKb": False
}
headers = {'Content-Type': 'application/json'}

r2 = requests.post(run_url, data=json.dumps(payload), headers=headers)
print(f"Run Status Code: {r2.status_code}")
print("Run Response Body (first 2000 chars):")
print(r2.text[:2000])

