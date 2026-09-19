from flask import Flask, request, jsonify, render_template_string, Response
import asyncio
import aiohttp
import json
import re
from base64 import b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

app = Flask(__name__)

# ==========================================
# 1. HTML FRONTEND (Mobile-Friendly Web App)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Appx Course Extractor</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; background: #f4f7f6; }
        .container { max-width: 450px; margin: auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0px 4px 10px rgba(0,0,0,0.1); }
        h2 { text-align: center; color: #333; }
        .btn { display: block; width: 100%; padding: 12px; margin-top: 15px; background: #28a745; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; font-weight: bold;}
        .btn:hover { background: #218838; }
        .btn:disabled { background: #ccc; cursor: not-allowed; }
        input, select { width: 95%; padding: 10px; margin-top: 10px; border: 1px solid #ccc; border-radius: 5px; font-size: 14px;}
        .loader { display: none; text-align: center; margin-top: 15px; font-weight: bold; color: #007bff; }
        #step2 { display: none; margin-top: 20px; border-top: 1px solid #eee; padding-top: 20px;}
    </style>
</head>
<body>
    <div class="container">
        <h2>📚 Appx Extractor App</h2>
        
        <label>Enter Appx API URL (https://...):</label>
        <input type="text" id="apiUrl" placeholder="https://api.example.com">
        
        <button class="btn" id="fetchBtn" onclick="fetchCourses()">Get Courses</button>
        <div class="loader" id="loader1">Fetching courses, please wait...</div>

        <div id="step2">
            <label>Select Course:</label>
            <select id="courseSelect"></select>
            
            <button class="btn" id="extractBtn" onclick="extractCourse()">Extract & Download</button>
            <div class="loader" id="loader2">Extracting data... This may take a few minutes.</div>
        </div>
    </div>

    <script>
        let coursesData = [];

        async function fetchCourses() {
            let apiUrl = document.getElementById("apiUrl").value.trim();
            if(!apiUrl) { alert("Please enter the API URL"); return; }
            if(!apiUrl.startsWith("http")) { apiUrl = "https://" + apiUrl; }

            document.getElementById("loader1").style.display = "block";
            document.getElementById("fetchBtn").disabled = true;
            document.getElementById("step2").style.display = "none";

            try {
                let response = await fetch('/api/get_courses', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_url: apiUrl })
                });
                
                let data = await response.json();
                
                if(data.success) {
                    coursesData = data.courses;
                    let select = document.getElementById("courseSelect");
                    select.innerHTML = "";
                    coursesData.forEach((c, index) => {
                        let opt = document.createElement("option");
                        opt.value = index;
                        opt.innerHTML = `${c.course_name} (₹${c.price})`;
                        select.appendChild(opt);
                    });
                    document.getElementById("step2").style.display = "block";
                } else {
                    alert("Error: " + data.error);
                }
            } catch (err) {
                alert("Failed to connect to server.");
            }
            document.getElementById("loader1").style.display = "none";
            document.getElementById("fetchBtn").disabled = false;
        }

        async function extractCourse() {
            let apiUrl = document.getElementById("apiUrl").value.trim();
            if(!apiUrl.startsWith("http")) { apiUrl = "https://" + apiUrl; }
            
            let selectedIndex = document.getElementById("courseSelect").value;
            let course = coursesData[selectedIndex];

            document.getElementById("loader2").style.display = "block";
            document.getElementById("extractBtn").disabled = true;

            try {
                let response = await fetch('/api/extract', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        api_url: apiUrl,
                        course_id: course.id,
                        folder_wise_course: course.folder_wise_course,
                        course_name: course.course_name
                    })
                });

                if (response.ok) {
                    let blob = await response.blob();
                    let link = document.createElement('a');
                    link.href = window.URL.createObjectURL(blob);
                    let cleanName = course.course_name.replace(/[^a-zA-Z0-9]/g, "_");
                    link.download = `${cleanName}.txt`;
                    link.click();
                } else {
                    let errData = await response.json();
                    alert("Error: " + errData.error);
                }
            } catch (err) {
                alert("Extraction failed.");
            }

            document.getElementById("loader2").style.display = "none";
            document.getElementById("extractBtn").disabled = false;
        }
    </script>
</body>
</html>
"""

# ==========================================
# 2. APPX BACKEND LOGIC (Core Extraction)
# ==========================================
TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpZCI6IjY1MjkzOTgiLCJ0aW1lc3RhbXAiOjE3ODM2NTg4MzQsIml2X3ZlciI6NjQsInNlc3Npb24iOiJleUowZVhBaU9pSktWMVFpTENKaGJHY2lPaUpJVXpJMU5pSjkuZXlKcFpDSTZJalkxTWprek9UZ2lMQ0psYldGcGJDSTZJbk4xY21WdVpISmhiRzlrYUdrME1UTkFaMjFoYVd3dVkyOXRJaXdpYm1GdFpTSTZJbE4xY21WdVpISmhJRXh2WkdocElpd2lkR1Z1WVc1MFZIbHdaU0k2SW5WelpYSWlMQ0owWlc1aGJuUk9ZVzFsSWpvaWNtOTZaMkZ5WDJSaUlpd2lkR1Z1WVc1MFNXUWlPaUlpTENKa2FYTndiM05oWW14bElqcG1ZV3h6WlgwLjZaYkV6LVVrVWlEOG1EVkNhZ1ZONXU2U3ZiX1dEcXgxcl9VdjlYcTJiREUifQ.XddzP9eIIAj-HT5xCHvcmR8bM-eyrzCZ2z-HdIkJwPk"
USERID = "6405136"

def get_headers():
    return {
        "Client-Service": "Appx",
        "Auth-Key": "appxapi",
        "source": "website",
        "Authorization": TOKEN,
        "User-ID": USERID,
        'User-Agent': "okhttp/4.9.1",
        'Accept-Encoding': "gzip"
    }

def appx_decrypt(enc):
    if not enc:
        return ""
    try:
        enc = b64decode(enc.split(':')[0])
        key = '638udh3829162018'.encode('utf-8')
        iv = 'fedcba9876543210'.encode('utf-8')
        if len(enc) == 0: return ""
        cipher = AES.new(key, AES.MODE_CBC, iv)
        plaintext = unpad(cipher.decrypt(enc), AES.block_size)
        return plaintext.decode('utf-8')
    except:
        return ""

async def fetch_appx_html_to_json(session, url, headers=None):
    try:
        async with session.get(url, headers=headers) as response:
            text = await response.text()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{"status":', text, re.DOTALL)
            if match:
                json_str = text[match.start():]
                open_brace = close_brace = 0
                for i, char in enumerate(json_str):
                    if char == '{': open_brace += 1
                    elif char == '}': close_brace += 1
                    if open_brace > 0 and open_brace == close_brace:
                        return json.loads(json_str[:i+1])
            return None
    except Exception as e:
        return None

async def fetch_appx_video_id_details_v2(session, api, selected_batch_id, video_id, ytFlag, headers, folder_wise_course):
    try:
        res = await fetch_appx_html_to_json(session, f"{api}/get/fetchVideoDetailsById?course_id={selected_batch_id}&folder_wise_course={folder_wise_course}&ytflag={ytFlag}&video_id={video_id}", headers)
        output = []
        if res and res.get('data'):
            data = res['data']
            Title = data["Title"]
            
            drm_res = await fetch_appx_html_to_json(session, f"{api}/get/get_mpd_drm_links?videoid={video_id}&folder_wise_course={folder_wise_course}", headers)
            if drm_res and drm_res.get('data') and len(drm_res['data']) > 0:
                path = appx_decrypt(drm_res['data'][0].get("path", ""))
                if path: output.append(f"{Title}:{path}\n")
                    
            pdf_link = appx_decrypt(data.get("pdf_link", ""))
            if pdf_link and pdf_link.endswith(".pdf"):
                if str(data.get("is_pdf_encrypted", 0)) == "1":
                    key = appx_decrypt(data.get("pdf_encryption_key", ""))
                    output.append(f"{Title}:{pdf_link}*{key}\n" if key else f"{Title}:{pdf_link}\n")
                else:
                    output.append(f"{Title}:{pdf_link}\n")
        return output
    except:
        return []

async def fetch_appx_folder_contents_v2(session, api, selected_batch_id, folder_id, headers, folder_wise_course):
    try:
        res = await fetch_appx_html_to_json(session, f"{api}/get/folder_contentsv2?course_id={selected_batch_id}&parent_id={folder_id}", headers)
        tasks, output = [], []
        if res and "data" in res:
            for item in res["data"]:
                if item.get("material_type") == "VIDEO":
                    tasks.append(fetch_appx_video_id_details_v2(session, api, selected_batch_id, item.get("id"), item.get("ytFlag"), headers, folder_wise_course))
                elif item.get("material_type") == "FOLDER":
                    tasks.append(fetch_appx_folder_contents_v2(session, api, selected_batch_id, item.get("id"), headers, folder_wise_course))
        
        if tasks:
            results = await asyncio.gather(*tasks)
            for r in results: output.extend(r)
        return output
    except:
        return []

async def process_folder_wise_course_0(session, api, selected_batch_id, headers):
    res = await fetch_appx_html_to_json(session, f"{api}/get/allsubjectfrmlivecourseclass?courseid={selected_batch_id}&start=-1", headers)
    all_outputs, tasks = [], []
    if res and "data" in res:
        for subject in res["data"]:
            res2 = await fetch_appx_html_to_json(session, f"{api}/get/alltopicfrmlivecourseclass?courseid={selected_batch_id}&subjectid={subject.get('subjectid')}&start=-1", headers)
            if res2 and "data" in res2:
                for topic in res2["data"]:
                    res3 = await fetch_appx_html_to_json(session, f"{api}/get/livecourseclassbycoursesubtopconceptapiv3?topicid={topic.get('topicid')}&start=-1&courseid={selected_batch_id}&subjectid={subject.get('subjectid')}", headers)
                    if res3 and "data" in res3:
                        for item in res3["data"]:
                            if item.get("material_type") == "VIDEO":
                                tasks.append(fetch_appx_video_id_details_v2(session, api, selected_batch_id, item.get("id"), item.get("ytFlag"), headers, 0))
    if tasks:
        results = await asyncio.gather(*tasks)
        for r in results: all_outputs.extend(r)
    return all_outputs

async def process_folder_wise_course_1(session, api, selected_batch_id, headers):
    res = await fetch_appx_html_to_json(session, f"{api}/get/folder_contentsv2?course_id={selected_batch_id}&parent_id=-1", headers)
    all_outputs, tasks = [], []
    if res and "data" in res:
        for item in res["data"]:
            if item.get("material_type") == "VIDEO":
                tasks.append(fetch_appx_video_id_details_v2(session, api, selected_batch_id, item.get("id"), item.get("ytFlag"), headers, 1))
            elif item.get("material_type") == "FOLDER":
                tasks.append(fetch_appx_folder_contents_v2(session, api, selected_batch_id, item.get("id"), headers, 1))
    
    if tasks:
        results = await asyncio.gather(*tasks)
        for r in results: all_outputs.extend(r)
    return all_outputs

# ==========================================
# 3. FLASK API ROUTES
# ==========================================
@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/get_courses', methods=['POST'])
def get_courses():
    api_url = request.json.get('api_url', '').rstrip('/')
    if not api_url: return jsonify({"success": False, "error": "API URL missing"})
    
    headers = get_headers()
    
    async def fetch_all():
        async with aiohttp.ClientSession() as session:
            res1 = await fetch_appx_html_to_json(session, f"{api_url}/get/courselist", headers)
            res2 = await fetch_appx_html_to_json(session, f"{api_url}/get/courselistnewv2", headers)
            
            c1 = res1.get("data", []) if res1 and res1.get('status') == 200 else []
            c2 = res2.get("data", []) if res2 and res2.get('status') == 200 else []
            return c1 + c2

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    courses = loop.run_until_complete(fetch_all())
    
    if not courses:
        return jsonify({"success": False, "error": "No courses found for this API"})
        
    return jsonify({"success": True, "courses": courses})

@app.route('/api/extract', methods=['POST'])
def extract_course():
    data = request.json
    api_url = data.get('api_url', '').rstrip('/')
    course_id = data.get('course_id')
    folder_wise = data.get('folder_wise_course', 0)
    
    headers = get_headers()

    async def run_extraction():
        async with aiohttp.ClientSession() as session:
            all_data = []
            if folder_wise == 0:
                all_data = await process_folder_wise_course_0(session, api_url, course_id, headers)
            elif folder_wise == 1:
                all_data = await process_folder_wise_course_1(session, api_url, course_id, headers)
            else:
                out0 = await process_folder_wise_course_0(session, api_url, course_id, headers)
                out1 = await process_folder_wise_course_1(session, api_url, course_id, headers)
                all_data = out0 + out1
            return "".join(all_data)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        final_text = loop.run_until_complete(run_extraction())
        if not final_text:
            return jsonify({"success": False, "error": "No data found in course"}), 404
            
        return Response(final_text, mimetype="text/plain", headers={"Content-Disposition": f"attachment;filename=course.txt"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
    
