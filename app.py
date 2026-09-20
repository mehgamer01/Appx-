from flask import Flask, request, jsonify, render_template_string, Response
import asyncio
import aiohttp
import json
import re
import uuid
import threading
from base64 import b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

app = Flask(__name__)

# Global Dictionary to store extraction progress
JOBS = {}

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
        .creds-box { background: #f9f9f9; padding: 15px; border-radius: 8px; margin-top: 10px; border: 1px solid #ddd; }
        
        /* Progress Bar CSS */
        #progressContainer { display: none; margin-top: 20px; background: #fff; border: 1px solid #ddd; padding: 15px; border-radius: 8px;}
        .progress-bar { width: 100%; background: #e9ecef; border-radius: 8px; overflow: hidden; height: 22px; border: 1px solid #ccc; margin-top: 5px;}
        .progress-fill { width: 0%; background: #28a745; height: 100%; transition: width 0.4s ease; }
        .progress-status { text-align: center; font-size: 14px; font-weight: bold; color: #444; margin-bottom: 5px;}
        .progress-text { text-align: center; font-size: 12px; font-weight: bold; color: #666; margin-top: 5px;}
    </style>
</head>
<body>
    <div class="container">
        <h2>📚 Appx Extractor App</h2>
        
        <label>Appx API URL (e.g., https://rozgarapinew.teachx.in):</label>
        <input type="text" id="apiUrl" placeholder="https://api.example.com">
        
        <div class="creds-box">
            <label>Mobile Number / Email:</label>
            <input type="text" id="phone" placeholder="Enter Mobile Number">
            
            <label>Password:</label>
            <input type="password" id="password" placeholder="Enter Password">
        </div>
        
        <button class="btn" id="fetchBtn" onclick="fetchCourses()">Login & Get Courses</button>
        <div class="loader" id="loader1">Logging in and fetching courses...</div>

        <div id="step2">
            <label>Select Course:</label>
            <select id="courseSelect"></select>
            
            <button class="btn" id="extractBtn" onclick="extractCourse()">Extract & Download</button>
            
            <!-- Progress Bar Section -->
            <div id="progressContainer">
                <div id="progressStatus" class="progress-status">Starting Extraction...</div>
                <div class="progress-bar">
                    <div id="progressFill" class="progress-fill"></div>
                </div>
                <div id="progressText" class="progress-text">0% (0 / 0 Videos)</div>
            </div>
            
        </div>
    </div>

    <script>
        let coursesData = [];
        let userToken = "";
        let userId = "";
        let pollingInterval = null;

        async function fetchCourses() {
            let apiUrl = document.getElementById("apiUrl").value.trim();
            let phone = document.getElementById("phone").value.trim();
            let password = document.getElementById("password").value.trim();

            if(!apiUrl) { alert("Please enter the API URL"); return; }
            if(!phone || !password) { alert("Please enter both Mobile Number and Password"); return; }
            if(!apiUrl.startsWith("http")) { apiUrl = "https://" + apiUrl; }

            document.getElementById("loader1").style.display = "block";
            document.getElementById("fetchBtn").disabled = true;
            document.getElementById("step2").style.display = "none";
            document.getElementById("progressContainer").style.display = "none";

            try {
                let response = await fetch('/api/login_and_get_courses', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_url: apiUrl, phone: phone, password: password })
                });
                
                let data = await response.json();
                
                if(data.success) {
                    coursesData = data.courses;
                    userToken = data.token;
                    userId = data.userid;
                    
                    let select = document.getElementById("courseSelect");
                    select.innerHTML = "";
                    coursesData.forEach((c, index) => {
                        let opt = document.createElement("option");
                        opt.value = index;
                        opt.innerHTML = `${c.course_name} (₹${c.price})`;
                        select.appendChild(opt);
                    });
                    document.getElementById("step2").style.display = "block";
                    alert("Login Successful!");
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

            document.getElementById("extractBtn").disabled = true;
            
            // Show Progress UI
            document.getElementById("progressContainer").style.display = "block";
            document.getElementById("progressStatus").innerText = "Connecting to Server...";
            document.getElementById("progressFill").style.width = "0%";
            document.getElementById("progressText").innerText = "0% (0 / 0 Videos)";

            try {
                let response = await fetch('/api/start_extract', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        api_url: apiUrl,
                        course_id: course.id,
                        folder_wise_course: course.folder_wise_course,
                        token: userToken,
                        userid: userId
                    })
                });

                let data = await response.json();
                
                if (data.task_id) {
                    pollingInterval = setInterval(() => checkProgress(data.task_id, course.course_name), 1500);
                } else {
                    alert("Error: " + data.error);
                    document.getElementById("extractBtn").disabled = false;
                }
            } catch (err) {
                alert("Failed to start extraction.");
                document.getElementById("extractBtn").disabled = false;
            }
        }

        async function checkProgress(taskId, courseName) {
            try {
                let res = await fetch('/api/progress/' + taskId);
                let data = await res.json();
                
                if (data.error) {
                    clearInterval(pollingInterval);
                    alert("Task Error: " + data.error);
                    document.getElementById("extractBtn").disabled = false;
                    return;
                }

                if (data.status === 'fetching_structure') {
                    document.getElementById("progressStatus").innerText = "Scanning Folders & PDFs (Please wait)...";
                } else if (data.status === 'extracting_videos') {
                    document.getElementById("progressStatus").innerText = "Extracting Video DRM Links...";
                }

                document.getElementById("progressFill").style.width = data.progress + "%";
                document.getElementById("progressText").innerText = `${data.progress}% (${data.completed} / ${data.total} Videos)`;

                if (data.status === 'completed') {
                    clearInterval(pollingInterval);
                    document.getElementById("progressStatus").innerText = "Extraction Complete! Downloading...";
                    document.getElementById("extractBtn").disabled = false;
                    
                    window.location.href = `/api/download/${taskId}?name=${encodeURIComponent(courseName)}`;
                } else if (data.status === 'error') {
                    clearInterval(pollingInterval);
                    document.getElementById("progressStatus").innerText = "Extraction Failed!";
                    alert("Error: " + data.error);
                    document.getElementById("extractBtn").disabled = false;
                }
            } catch(e) {
                console.log("Polling error... retrying...");
            }
        }
    </script>
</body>
</html>
"""

# ==========================================
# 2. APPX BACKEND LOGIC & DECRYPTION
# ==========================================

def get_headers(token, userid):
    return {
        "Client-Service": "Appx",
        "Auth-Key": "appxapi",
        "source": "website",
        "Device-Type": "web",
        "io-Safari": "0",
        "Authorization": token,
        "User-ID": str(userid),
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        'Accept-Encoding': "gzip, deflate, br"
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

async def fetch_appx_html_to_json(session, url, headers=None, data=None):
    try:
        if data:
            async with session.post(url, headers=headers, data=data) as response:
                text = await response.text()
        else:
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

# ==========================================
# 3. FAST STRUCTURE FETCHING (PHASE 1)
# ==========================================

async def collect_folder_0(session, api, course_id, headers):
    video_items = []
    other_outputs = []
    res = await fetch_appx_html_to_json(session, f"{api}/get/allsubjectfrmlivecourseclass?courseid={course_id}&start=-1", headers)
    if res and "data" in res:
        for subject in res["data"]:
            sub_id = subject.get("subjectid")
            res2 = await fetch_appx_html_to_json(session, f"{api}/get/alltopicfrmlivecourseclass?courseid={course_id}&subjectid={sub_id}&start=-1", headers)
            if res2 and "data" in res2:
                for topic in res2["data"]:
                    top_id = topic.get("topicid")
                    url_v3 = f"{api}/get/livecourseclassbycoursesubtopconceptapiv3?courseid={course_id}&subjectid={sub_id}&topicid={top_id}&conceptid=&windowapp=false&start=-1"
                    res3 = await fetch_appx_html_to_json(session, url_v3, headers)
                    
                    if res3 and "data" in res3:
                        for item in res3["data"]:
                            m_type = item.get("material_type")
                            if m_type == "VIDEO":
                                item['folder_wise'] = 0
                                video_items.append(item)
                            elif m_type in ("PDF", "TEST"):
                                title = item.get("Title", "Untitled")
                                pdf_link = appx_decrypt(item.get("pdf_link", ""))
                                if pdf_link:
                                    if str(item.get("is_pdf_encrypted", 0)) == "1":
                                        key = appx_decrypt(item.get("pdf_encryption_key", ""))
                                        other_outputs.append(f"{title}:{pdf_link}*{key}\n" if key else f"{title}:{pdf_link}\n")
                                    else:
                                        other_outputs.append(f"{title}:{pdf_link}\n")
    return video_items, other_outputs

async def collect_folder_1(session, api, course_id, parent_id, headers):
    video_items = []
    other_outputs = []
    res = await fetch_appx_html_to_json(session, f"{api}/get/folder_contentsv2?course_id={course_id}&parent_id={parent_id}", headers)
    if res and "data" in res:
        for item in res["data"]:
            m_type = item.get("material_type")
            if m_type == "VIDEO":
                item['folder_wise'] = 1
                video_items.append(item)
            elif m_type == "FOLDER":
                sub_vids, sub_outs = await collect_folder_1(session, api, course_id, item.get("id"), headers)
                video_items.extend(sub_vids)
                other_outputs.extend(sub_outs)
            elif m_type in ("PDF", "TEST"):
                title = item.get("Title", "Untitled")
                pdf_link = appx_decrypt(item.get("pdf_link", ""))
                if pdf_link:
                    if str(item.get("is_pdf_encrypted", 0)) == "1":
                        key = appx_decrypt(item.get("pdf_encryption_key", ""))
                        other_outputs.append(f"{title}:{pdf_link}*{key}\n" if key else f"{title}:{pdf_link}\n")
                    else:
                        other_outputs.append(f"{title}:{pdf_link}\n")
    return video_items, other_outputs

# ==========================================
# 4. SLOW DRM EXTRACTION (PHASE 2)
# ==========================================

async def fetch_appx_video_id_details_v2(session, api, selected_batch_id, video_id, ytFlag, headers, folder_wise_course):
    try:
        fetch_url = f"{api}/get/fetchVideoDetailsById?course_id={selected_batch_id}&folder_wise_course={folder_wise_course}&ytflag={ytFlag}&video_id={video_id}&c_app_api_url="
        res = await fetch_appx_html_to_json(session, fetch_url, headers)
        
        output = []
        if res and res.get('data'):
            data = res['data']
            Title = data.get("Title", "Untitled")
            
            drm_res = await fetch_appx_html_to_json(session, f"{api}/get/get_mpd_drm_links?videoid={video_id}&folder_wise_course={folder_wise_course}", headers)
            if drm_res and drm_res.get('data') and len(drm_res['data']) > 0:
                path = appx_decrypt(drm_res['data'][0].get("path", ""))
                if path: output.append(f"{Title}:{path}\n")
                    
            pdf_link = appx_decrypt(data.get("pdf_link", ""))
            if pdf_link:
                if str(data.get("is_pdf_encrypted", 0)) == "1":
                    key = appx_decrypt(data.get("pdf_encryption_key", ""))
                    output.append(f"{Title}:{pdf_link}*{key}\n" if key else f"{Title}:{pdf_link}\n")
                else:
                    output.append(f"{Title}:{pdf_link}\n")
        return output
    except:
        return []

# ==========================================
# 5. BACKGROUND EXTRACTION THREAD LOGIC
# ==========================================

async def run_extraction_logic(task_id, data):
    api_url = data.get('api_url', '').rstrip('/')
    course_id = data.get('course_id')
    folder_wise = data.get('folder_wise_course', 0)
    token = data.get('token')
    userid = data.get('userid')
    
    headers = get_headers(token, userid)

    async with aiohttp.ClientSession() as session:
        JOBS[task_id]['status'] = 'fetching_structure'
        video_items = []
        final_outputs = []
        
        if folder_wise == 0:
            vids, outs = await collect_folder_0(session, api_url, course_id, headers)
            video_items.extend(vids)
            final_outputs.extend(outs)
        elif folder_wise == 1:
            vids, outs = await collect_folder_1(session, api_url, course_id, "-1", headers)
            video_items.extend(vids)
            final_outputs.extend(outs)
        else:
            vids0, outs0 = await collect_folder_0(session, api_url, course_id, headers)
            vids1, outs1 = await collect_folder_1(session, api_url, course_id, "-1", headers)
            video_items.extend(vids0 + vids1)
            final_outputs.extend(outs0 + outs1)

        JOBS[task_id]['total'] = len(video_items)
        JOBS[task_id]['status'] = 'extracting_videos'
        
        if len(video_items) > 0:
            tasks = [fetch_appx_video_id_details_v2(session, api_url, course_id, v['id'], v.get('ytFlag', 0), headers, v.get('folder_wise', folder_wise)) for v in video_items]
            
            for coro in asyncio.as_completed(tasks):
                res = await coro
                if res:
                    final_outputs.extend(res)
                
                JOBS[task_id]['completed'] += 1
                JOBS[task_id]['progress'] = int((JOBS[task_id]['completed'] / JOBS[task_id]['total']) * 100)
        else:
            JOBS[task_id]['progress'] = 100

        if not final_outputs:
            JOBS[task_id]['error'] = "No data found in this course."
            JOBS[task_id]['status'] = 'error'
        else:
            JOBS[task_id]['result'] = "".join(final_outputs)
            JOBS[task_id]['status'] = 'completed'


def background_task(task_id, data):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_extraction_logic(task_id, data))
    except Exception as e:
        JOBS[task_id]['error'] = str(e)
        JOBS[task_id]['status'] = 'error'
    finally:
        loop.close()

# ==========================================
# 6. FLASK API ROUTES
# ==========================================
@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/login_and_get_courses', methods=['POST'])
def login_and_get_courses():
    data = request.json
    api_url = data.get('api_url', '').rstrip('/')
    phone = data.get('phone')
    password = data.get('password')
    
    if not api_url or not phone or not password: 
        return jsonify({"success": False, "error": "Missing API URL, Phone, or Password"})
    
    async def perform_login_and_fetch():
        async with aiohttp.ClientSession() as session:
            login_url = f"{api_url}/post/userLogin"
            login_payload = f"email={phone}&password={password}"
            
            login_headers = {
                'Auth-Key': 'appxapi',
                'User-Id': '-2',
                'Authorization': '',
                'Language': 'en',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept-Encoding': 'gzip, deflate',
                'User-Agent': 'okhttp/4.9.1'
            }
            
            login_res = await fetch_appx_html_to_json(session, login_url, headers=login_headers, data=login_payload)
            token, userid = None, None

            if login_res and login_res.get("status") == 200:
                token = login_res.get("data", {}).get("token", "")
                userid = login_res.get("data", {}).get("userid", "")
            else:
                login_headers_web = {
                    'Client-Service': 'Appx',
                    'source': 'website',
                    'Auth-Key': 'appxapi',
                    'Authorization': '',
                    'User-ID': '-2',
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 12) Chrome/124.0.0.0 Mobile Safari/537.36'
                }
                login_res2 = await fetch_appx_html_to_json(session, login_url, headers=login_headers_web, data=login_payload)
                if login_res2 and login_res2.get("status") == 200:
                    token = login_res2.get("data", {}).get("token", "")
                    userid = login_res2.get("data", {}).get("userid", "")

            if not token or not userid:
                error_msg = login_res.get("message", "Login Failed") if login_res else "Invalid Credentials or App Update"
                return {"success": False, "error": error_msg}
                
            headers = get_headers(token, userid)
            res1 = await fetch_appx_html_to_json(session, f"{api_url}/get/mycoursev2", headers)
            res2 = await fetch_appx_html_to_json(session, f"{api_url}/get/mycourse", headers)
            
            if not res1 and not res2:
                res1 = await fetch_appx_html_to_json(session, f"{api_url}/get/courselist", headers)
            
            c1 = res1.get("data", []) if res1 and res1.get('status') == 200 else []
            c2 = res2.get("data", []) if res2 and res2.get('status') == 200 else []
            
            if isinstance(c1, dict) and "courses" in c1: c1 = c1["courses"]
            if isinstance(c2, dict) and "courses" in c2: c2 = c2["courses"]
            
            courses = c1 + c2
            
            if not courses:
                return {"success": False, "error": "Login successful, but no enrolled courses found"}
                
            return {"success": True, "courses": courses, "token": token, "userid": userid}

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(perform_login_and_fetch())
    return jsonify(result)

@app.route('/api/start_extract', methods=['POST'])
def start_extract():
    task_id = str(uuid.uuid4())
    JOBS[task_id] = {'progress': 0, 'total': 0, 'completed': 0, 'status': 'starting', 'result': None, 'error': None}
    threading.Thread(target=background_task, args=(task_id, request.json)).start()
    return jsonify({"task_id": task_id})

@app.route('/api/progress/<task_id>', methods=['GET'])
def get_progress(task_id):
    if task_id not in JOBS:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(JOBS[task_id])

@app.route('/api/download/<task_id>', methods=['GET'])
def download_result(task_id):
    if task_id not in JOBS or JOBS[task_id]['status'] != 'completed':
        return "File not ready", 400
    
    result = JOBS[task_id]['result']
    course_name = request.args.get('name', 'Course')
    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', course_name)
    
    del JOBS[task_id] 
    return Response(result, mimetype="text/plain", headers={"Content-Disposition": f"attachment;filename={clean_name}.txt"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
