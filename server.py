"""
AI Agent Backend Server
Handles: terminal commands, video editing (FFmpeg), code execution,
YouTube uploads & analytics via YouTube Data API v3
"""

import os
import subprocess
import json
import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Optional

from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from flask_cors import CORS
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.http
from googleapiclient.errors import HttpError

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-me-in-production")
CORS(app)

# ── OAuth2 / YouTube Setup ────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
CLIENT_SECRETS_FILE = "client_secrets.json"  # Download from Google Cloud Console
REDIRECT_URI = "http://localhost:5000/oauth2callback"

# In-memory credential store (use Redis/DB in production)
_credentials: Optional[google.oauth2.credentials.Credentials] = None


def get_youtube_client():
    if _credentials is None:
        raise RuntimeError("Not authenticated. Visit /auth/login first.")
    return googleapiclient.discovery.build("youtube", "v3", credentials=_credentials)


# ── Auth Routes ───────────────────────────────────────────────────────────────
@app.route("/auth/login")
def auth_login():
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES
    )
    flow.redirect_uri = REDIRECT_URI
    auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true")
    return jsonify({"auth_url": auth_url})


@app.route("/oauth2callback")
def oauth2callback():
    global _credentials
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES
    )
    flow.redirect_uri = REDIRECT_URI
    flow.fetch_token(authorization_response=request.url)
    _credentials = flow.credentials
    return "<script>window.close()</script><p>Auth complete! Close this tab.</p>"


@app.route("/auth/status")
def auth_status():
    return jsonify({"authenticated": _credentials is not None})


# ── Terminal Command Execution ────────────────────────────────────────────────
@app.route("/api/terminal", methods=["POST"])
def run_terminal():
    """Execute a shell command and stream output."""
    data = request.json
    cmd = data.get("command", "").strip()
    cwd = data.get("cwd", str(Path.home()))

    if not cmd:
        return jsonify({"error": "No command provided"}), 400

    # Block dangerous commands
    blocked = ["rm -rf /", "mkfs", ":(){:|:&};:", "sudo rm -rf"]
    for b in blocked:
        if b in cmd:
            return jsonify({"error": f"Blocked command: {b}"}), 403

    def generate():
        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=cwd,
                bufsize=1,
            )
            for line in iter(proc.stdout.readline, ""):
                yield f"data: {json.dumps({'line': line.rstrip()})}\n\n"
            proc.wait()
            yield f"data: {json.dumps({'exit_code': proc.returncode, 'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


# ── Code Execution ────────────────────────────────────────────────────────────
@app.route("/api/code/run", methods=["POST"])
def run_code():
    """Execute Python code in a temp file and return stdout/stderr."""
    data = request.json
    code = data.get("code", "")
    language = data.get("language", "python")  # python | bash

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py" if language == "python" else ".sh",
        delete=False,
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        cmd = ["python3", tmp_path] if language == "python" else ["bash", tmp_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return jsonify({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timeout: code ran > 30 seconds"}), 408
    finally:
        os.unlink(tmp_path)


# ── Video Editing (FFmpeg) ────────────────────────────────────────────────────
@app.route("/api/video/trim", methods=["POST"])
def video_trim():
    data = request.json
    inp = data["input"]
    out = data.get("output", "output_trimmed.mp4")
    start = data.get("start", "0")
    duration = data.get("duration", "10")
    cmd = f'ffmpeg -y -i "{inp}" -ss {start} -t {duration} -c copy "{out}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return jsonify({"command": cmd, "stdout": result.stdout, "stderr": result.stderr,
                    "success": result.returncode == 0, "output_file": out})


@app.route("/api/video/convert", methods=["POST"])
def video_convert():
    data = request.json
    inp = data["input"]
    out = data.get("output", "output.mp4")
    cmd = f'ffmpeg -y -i "{inp}" "{out}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return jsonify({"command": cmd, "success": result.returncode == 0, "output_file": out})


@app.route("/api/video/merge", methods=["POST"])
def video_merge():
    data = request.json
    files = data["files"]          # list of paths
    out = data.get("output", "merged.mp4")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for fp in files:
            f.write(f"file '{fp}'\n")
        list_path = f.name
    cmd = f'ffmpeg -y -f concat -safe 0 -i "{list_path}" -c copy "{out}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    os.unlink(list_path)
    return jsonify({"command": cmd, "success": result.returncode == 0, "output_file": out})


@app.route("/api/video/thumbnail", methods=["POST"])
def video_thumbnail():
    data = request.json
    inp = data["input"]
    out = data.get("output", "thumbnail.jpg")
    timestamp = data.get("timestamp", "00:00:01")
    cmd = f'ffmpeg -y -i "{inp}" -ss {timestamp} -vframes 1 "{out}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return jsonify({"command": cmd, "success": result.returncode == 0, "output_file": out})


@app.route("/api/video/info", methods=["POST"])
def video_info():
    data = request.json
    inp = data["input"]
    cmd = f'ffprobe -v quiet -print_format json -show_format -show_streams "{inp}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    try:
        return jsonify({"info": json.loads(result.stdout)})
    except Exception:
        return jsonify({"error": result.stderr}), 400


# ── YouTube Upload ────────────────────────────────────────────────────────────
@app.route("/api/youtube/upload", methods=["POST"])
def youtube_upload():
    data = request.json
    file_path = data.get("file_path")
    title = data.get("title", "Untitled Video")
    description = data.get("description", "")
    tags = data.get("tags", [])
    privacy = data.get("privacy", "private")  # private | unlisted | public
    category_id = data.get("category_id", "22")  # 22 = People & Blogs

    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 400

    try:
        yt = get_youtube_client()
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": category_id,
            },
            "status": {"privacyStatus": privacy},
        }
        media = googleapiclient.http.MediaFileUpload(
            file_path, chunksize=-1, resumable=True, mimetype="video/*"
        )
        insert_request = yt.videos().insert(
            part=",".join(body.keys()), body=body, media_body=media
        )
        response = None
        while response is None:
            _, response = insert_request.next_chunk()
        return jsonify({"video_id": response["id"], "url": f"https://youtu.be/{response['id']}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── YouTube Analytics ─────────────────────────────────────────────────────────
@app.route("/api/youtube/channel", methods=["GET"])
def channel_info():
    try:
        yt = get_youtube_client()
        res = yt.channels().list(part="snippet,statistics,brandingSettings", mine=True).execute()
        items = res.get("items", [])
        if not items:
            return jsonify({"error": "No channel found"}), 404
        ch = items[0]
        stats = ch.get("statistics", {})
        snip = ch.get("snippet", {})
        return jsonify({
            "id": ch["id"],
            "title": snip.get("title"),
            "description": snip.get("description"),
            "subscribers": int(stats.get("subscriberCount", 0)),
            "views": int(stats.get("viewCount", 0)),
            "videos": int(stats.get("videoCount", 0)),
            "thumbnail": snip.get("thumbnails", {}).get("default", {}).get("url"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/youtube/videos", methods=["GET"])
def recent_videos():
    max_results = int(request.args.get("max", 10))
    try:
        yt = get_youtube_client()
        channels_res = yt.channels().list(part="contentDetails", mine=True).execute()
        playlist_id = channels_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        playlist_res = yt.playlistItems().list(
            part="snippet", playlistId=playlist_id, maxResults=max_results
        ).execute()
        videos = []
        for item in playlist_res.get("items", []):
            snip = item["snippet"]
            videos.append({
                "id": snip["resourceId"]["videoId"],
                "title": snip["title"],
                "published": snip["publishedAt"],
                "thumbnail": snip.get("thumbnails", {}).get("medium", {}).get("url"),
                "url": f"https://youtu.be/{snip['resourceId']['videoId']}",
            })
        return jsonify({"videos": videos})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/youtube/analytics", methods=["GET"])
def video_analytics():
    video_id = request.args.get("video_id")
    try:
        yt = get_youtube_client()
        stats_res = yt.videos().list(part="statistics,snippet", id=video_id).execute()
        if not stats_res.get("items"):
            return jsonify({"error": "Video not found"}), 404
        item = stats_res["items"][0]
        stats = item["statistics"]
        return jsonify({
            "video_id": video_id,
            "title": item["snippet"]["title"],
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
            "favorites": int(stats.get("favoriteCount", 0)),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Frontend ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)