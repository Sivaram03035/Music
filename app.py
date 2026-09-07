from flask import Flask, render_template, request, jsonify
import innertube
import yt_dlp
import re
import os
import logging
import time

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

# YouTube Music search
client = innertube.InnerTube("WEB_REMIX")


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def extract_text(runs):
    return "".join(
        run.get("text", "")
        for run in runs
        if isinstance(run, dict)
    )


def parse_search_results(data):
    results = []

    def walk(obj):

        if isinstance(obj, dict):

            renderer = obj.get(
                "musicResponsiveListItemRenderer"
            )

            if renderer:

                title = "Unknown"

                flex_columns = renderer.get(
                    "flexColumns", []
                )

                # -----------------------------
                # Title
                # -----------------------------

                if flex_columns:

                    column = flex_columns[0].get(
                        "musicResponsiveListItemFlexColumnRenderer",
                        {}
                    )

                    text = column.get(
                        "text",
                        {}
                    )

                    runs = text.get(
                        "runs",
                        []
                    )

                    if runs:
                        title = extract_text(runs)

                # -----------------------------
                # Subtitle
                # -----------------------------

                subtitle = ""

                if len(flex_columns) > 1:

                    column = flex_columns[1].get(
                        "musicResponsiveListItemFlexColumnRenderer",
                        {}
                    )

                    text = column.get(
                        "text",
                        {}
                    )

                    runs = text.get(
                        "runs",
                        []
                    )

                    subtitle = " • ".join(
                        run.get("text", "")
                        for run in runs
                        if run.get("text") not in (" • ", "")
                    )

                # -----------------------------
                # Video ID
                # -----------------------------

                video_id = (
                    renderer
                    .get("playlistItemData", {})
                    .get("videoId")
                )

                # Some results store it elsewhere
                if not video_id:

                    overlay = (
                        renderer
                        .get("overlay", {})
                        .get(
                            "musicItemThumbnailOverlayRenderer",
                            {}
                        )
                    )

                    play_button = (
                        overlay
                        .get("content", {})
                        .get(
                            "musicPlayButtonRenderer",
                            {}
                        )
                    )

                    endpoint = play_button.get(
                        "playNavigationEndpoint",
                        {}
                    )

                    watch = endpoint.get(
                        "watchEndpoint"
                    )

                    if watch:
                        video_id = watch.get(
                            "videoId"
                        )

                if video_id:

                    results.append({
                        "title": title,
                        "subtitle": subtitle,
                        "videoId": video_id,
                        "url":
                            f"https://www.youtube.com/watch?v={video_id}"
                    })

            for value in obj.values():
                walk(value)

        elif isinstance(obj, list):

            for item in obj:
                walk(item)

    walk(data)

    # Remove duplicates
    unique = []
    seen = set()

    for item in results:

        video_id = item["videoId"]

        if video_id not in seen:

            seen.add(video_id)
            unique.append(item)

    return unique


# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------
# Search
# ---------------------------------------------------------

@app.route("/search")
def search():

    query = request.args.get(
        "q",
        ""
    ).strip()

    if not query:
        return jsonify([])

    try:

        logging.info(
            "Searching YouTube Music: %s",
            query
        )

        data = client.search(
            query=query
        )

        results = parse_search_results(
            data
        )

        return jsonify(
            results[:30]
        )

    except Exception as e:

        logging.exception(
            "Search failed"
        )

        return jsonify({
            "error": str(e)
        }), 500


# ---------------------------------------------------------
# Stream
# ---------------------------------------------------------

@app.route("/stream/<video_id>")
def stream(video_id):

    # YouTube IDs are 11 characters
    if not re.fullmatch(
        r"[A-Za-z0-9_-]{11}",
        video_id
    ):
        return jsonify({
            "error": "Invalid video ID"
        }), 400

    youtube_url = (
        "https://www.youtube.com/watch?v="
        + video_id
    )

    # -----------------------------------------------------
    # yt-dlp configuration
    # -----------------------------------------------------

    options = {

        # Audio only
        "format":
            "bestaudio[ext=m4a]/"
            "bestaudio",

        "quiet": True,
        "no_warnings": True,

        "noplaylist": True,

        # Allow yt-dlp EJS scripts
        "remote_components":
            "ejs:github",

        # Current recommended YouTube client
        "extractor_args": {
            "youtube": {
                "player_client": [
                    "mweb"
                ]
            }
        },

        # Browser-like headers
        "http_headers": {
            "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0.0.0 "
                "Safari/537.36"
        },

        # Do not download the media
        "skip_download": True,

        # Socket timeout
        "socket_timeout": 20,

        # Retries
        "retries": 2,
    }

    try:

        logging.info(
            "Extracting audio: %s",
            video_id
        )

        with yt_dlp.YoutubeDL(
            options
        ) as ydl:

            info = ydl.extract_info(
                youtube_url,
                download=False
            )

        stream_url = info.get(
            "url"
        )

        if not stream_url:

            return jsonify({
                "error":
                    "No audio stream was returned"
            }), 404

        return jsonify({

            "videoId":
                video_id,

            "title":
                info.get("title"),

            "url":
                stream_url,

            "duration":
                info.get("duration"),

            "thumbnail":
                info.get("thumbnail"),

            "mimeType":
                info.get("mime_type"),

            "ext":
                info.get("ext"),

            "expires":
                int(
                    time.time()
                ) + 300

        })

    except Exception as e:

        logging.exception(
            "Stream extraction failed"
        )

        return jsonify({

            "error":
                str(e),

            "videoId":
                video_id

        }), 500


# ---------------------------------------------------------
# Health check
# ---------------------------------------------------------

@app.route("/health")
def health():

    return jsonify({
        "status": "ok",
        "service": "yt-music-api"
    })


# ---------------------------------------------------------
# Debug / version
# ---------------------------------------------------------

@app.route("/api/info")
def api_info():

    return jsonify({

        "service":
            "YT Music Player API",

        "yt_dlp":
            yt_dlp.version.__version__,

        "pot_provider":
            bool(
                os.environ.get(
                    "YTDL_POT_PROVIDER_URL"
                )
            )

    })


# ---------------------------------------------------------
# Local development
# ---------------------------------------------------------

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
