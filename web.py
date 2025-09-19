import shutil
from fastapi import FastAPI, UploadFile
from fastapi.responses import HTMLResponse, FileResponse
from transcribe_with_whisper.core import transcribe_file

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <html>
        <body>
            <h1>Whisper Transcriber</h1>
            <form action="/upload" enctype="multipart/form-data" method="post">
                <input type="file" name="file" accept="audio/*,video/*">
                <br><br>
                <input type="submit" value="Transcribe">
            </form>
        </body>
    </html>
    """

@app.post("/upload")
async def upload(file: UploadFile):
    input_path = f"/tmp/{file.filename}"
    output_html = input_path + ".html"

    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    transcribe_file(input_path, output_html)

    return FileResponse(output_html, media_type="text/html", filename=file.filename + ".html")

