from flask import Flask, render_template, request, jsonify
import innertube
import yt_dlp
import re

app = Flask(__name__)

client = innertube.InnerTube("WEB_REMIX")


def extract_text(runs):
    return "".join(
        run.get("text", "")
        for run in runs
    )


def parse_search_results(data):
    results = []

    def walk(obj):
        if isinstance(obj, dict):

            renderer = obj.get("musicResponsiveListItemRenderer")

            if renderer:
                title = "Unknown"

                flex_columns = renderer.get("flexColumns", [])

                # -------------------------
                # Title
                # -------------------------
                if flex_columns:
                    column = flex_columns[0].get(
                        "musicResponsiveListItemFlexColumnRenderer",
                        {}
                    )

                    text = column.get("text", {})
                    runs = text.get("runs", [])

                    if runs:
                        title = extract_text(runs)

                # -------------------------
                # Subtitle
                # -------------------------
                subtitle = ""

                if len(flex_columns) > 1:
                    column = flex_columns[1].get(
                        "musicResponsiveListItemFlexColumnRenderer",
                        {}
                    )

                    text = column.get("text", {})
                    runs = text.get("runs", [])

                    subtitle = " • ".join(
                        run.get("text", "")
                        for run in runs
                        if run.get("text") not in (" • ", "")
                    )

                # -------------------------
                # Video ID
                # -------------------------
                video_id = (
                    renderer
                    .get("playlistItemData", {})
                    .get("videoId")
                )

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
                        .get("musicPlayButtonRenderer", {})
                    )

                    endpoint = play_button.get(
                        "playNavigationEndpoint",
                        {}
                    )

                    watch = endpoint.get("watchEndpoint")

                    if watch:
                        video_id = watch.get("videoId")

                if video_id:
                    results.append({
                        "title": title,
                        "subtitle": subtitle,
                        "videoId": video_id,
                        "url": f"https://www.youtube.com/watch?v={video_id}"
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
        if item["videoId"] not in seen:
            seen.add(item["videoId"])
            unique.append(item)

    return unique


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify([])

    try:
        data = client.search(query=query)
        results = parse_search_results(data)

        return jsonify(results[:30])

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


@app.route("/stream/<video_id>")
def stream(video_id):
    # Basic validation
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return jsonify({"error": "Invalid video ID"}), 400

    url = f"https://www.youtube.com/watch?v={video_id}"

    options = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                url,
                download=False
            )

        stream_url = info.get("url")

        if not stream_url:
            return jsonify({
                "error": "No audio stream found"
            }), 404

        return jsonify({
            "videoId": video_id,
            "title": info.get("title"),
            "url": stream_url,
            "duration": info.get("duration")
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )