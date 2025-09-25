import sys
import os
import subprocess
from pathlib import Path
from pyannote.audio import Pipeline
from pydub import AudioSegment
from faster_whisper import WhisperModel
import webvtt
import re
import warnings
try:
    import torchaudio  # type: ignore
    _HAS_TORCHAUDIO = True
except Exception:
    _HAS_TORCHAUDIO = False

warnings.filterwarnings("ignore", message="Model was trained with")
warnings.filterwarnings("ignore", message="Lightning automatically upgraded")

def millisec(timeStr):
    spl = timeStr.split(":")
    s = int((int(spl[0]) * 3600 + int(spl[1]) * 60 + float(spl[2])) * 1000)
    return s

def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

def convert_to_wav(inputfile, outputfile):
    if not os.path.isfile(outputfile):
        subprocess.run(["ffmpeg", "-i", inputfile, outputfile])

def create_spaced_audio(inputWav, outputWav, spacer_ms=2000):
    audio = AudioSegment.from_wav(inputWav)
    spacer = AudioSegment.silent(duration=spacer_ms)
    audio = spacer.append(audio, crossfade=0)
    audio.export(outputWav, format="wav")

def get_diarization(inputWav, diarizationFile):
    auth_token = os.getenv("HUGGING_FACE_AUTH_TOKEN")
    if not auth_token:
        raise ValueError("HUGGING_FACE_AUTH_TOKEN environment variable is required")

    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=auth_token)

    if not os.path.isfile(diarizationFile):
        if _HAS_TORCHAUDIO:
            # Load audio into memory for faster processing
            waveform, sample_rate = torchaudio.load(inputWav)
            dz = pipeline({"waveform": waveform, "sample_rate": sample_rate})
        else:
            # Fallback to file path if torchaudio is not available
            dz = pipeline({"uri": "blabla", "audio": inputWav})
        with open(diarizationFile, "w") as f:
            f.write(str(dz))
    with open(diarizationFile) as f:
        return f.read().splitlines()

def group_segments(dzs):
    groups, g, lastend = [], [], 0
    for d in dzs:
        if g and g[0].split()[-1] != d.split()[-1]:
            groups.append(g)
            g = []
        g.append(d)
        end = millisec(re.findall(r"[0-9]+:[0-9]+:[0-9]+\.[0-9]+", d)[1])
        if lastend > end:
            groups.append(g)
            g = []
        else:
            lastend = end
    if g:
        groups.append(g)
    return groups

def export_segments_audio(groups, inputWav, spacermilli=2000):
    audio = AudioSegment.from_wav(inputWav)
    segment_files = []
    for idx, g in enumerate(groups):
        start = millisec(re.findall(r"[0-9]+:[0-9]+:[0-9]+\.[0-9]+", g[0])[0])
        end = millisec(re.findall(r"[0-9]+:[0-9]+:[0-9]+\.[0-9]+", g[-1])[1])
        audio[start:end].export(f"{idx}.wav", format="wav")
        segment_files.append(f"{idx}.wav")
    return segment_files

def transcribe_segments(segment_files):
    model = WhisperModel("base", device="auto", compute_type="auto")
    for f in segment_files:
        vtt_file = f"{Path(f).stem}.vtt"
        if not os.path.isfile(vtt_file):
            segments, _ = model.transcribe(f, language="en")
            with open(vtt_file, "w", encoding="utf-8") as out:
                out.write("WEBVTT\n\n")
                for s in segments:
                    out.write(f"{format_time(s.start)} --> {format_time(s.end)}\n{s.text.strip()}\n\n")
    return [f"{Path(f).stem}.vtt" for f in segment_files]

def generate_html(outputHtml, groups, vtt_files, inputfile, speakers, spacermilli=2000):
    # video_title is inputfile with no extension
    video_title = os.path.splitext(inputfile)[0]
    html = []
    preS = f"""<!DOCTYPE html>\n<html lang="en">\n  <head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="ie=edge">
    <title>{inputfile}</title>
    <style>
        body {{
            font-family: sans-serif;
            font-size: 18px;
            color: #111;
            padding: 0 0 1em 0;
	        background-color: #efe7dd;
        }}
        table {{
             border-spacing: 10px;
        }}
        th {{ text-align: left;}}
        .lt {{
          color: inherit;
          text-decoration: inherit;
        }}
        .l {{
          color: #050;
        }}
        .s {{
            display: inline-block;
        }}
        .c {{
            display: inline-block;
        }}
        .e {{
            border-radius: 20px;
            width: fit-content;
            height: fit-content;
            padding: 5px 30px 5px 30px;
            font-size: 18px;
            display: flex;
            flex-direction: column;
            margin-bottom: 10px;
        }}

        .t {{
            display: inline-block;
        }}
        #video-header {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            width: 100%;
            background: #efe7dd;
            z-index: 1000;
            padding: 10px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        #player {{
            display: block;
            margin: 0 auto;
        }}
        #content {{
            margin-top: 280px;
        }}
        .timestamp {{
            color: #666;
            font-size: 14px;
            font-weight: bold;
        }}
        .speaker-name {{
            font-weight: bold;
            margin-right: 8px;
        }}
    </style>
</head>
  <body>
   """ + f"""
    <div id="video-header" class="html-only">
    <h2 style="text-align: center; margin: 5px 0;">{video_title}</h2>
    <p style="text-align: center; margin: 5px 0; font-style: italic;">Click on a word to jump to that section of the video</p>
    <video id="player" style="border:none;" width="575" height="240" preload controls>
      <source src="{inputfile}" type="video/mp4; codecs=avc1.42E01E,mp4a.40.2" />
    </video>
    </div>
    <div id="content">
  <div class="e" style="background-color: white">
  """
    html.append(preS)
    def_boxclr, def_spkrclr = "white", "orange"

    for idx, g in enumerate(groups):
        shift = max(millisec(re.findall(r"[0-9]+:[0-9]+:[0-9]+\.[0-9]+", g[0])[0]) - spacermilli, 0)
        speaker = g[0].split()[-1]
        spkr_name, boxclr, spkrclr = speakers.get(speaker, (speaker, def_boxclr, def_spkrclr))
        html.append(f'    <div class="e" style="background-color:{boxclr}"><span style="color:{spkrclr}">{spkr_name}</span><br>')
        captions = [[int(millisec(c.start)), int(millisec(c.end)), c.text] for c in webvtt.read(vtt_files[idx])]
        for c in captions:
            start_sec = (shift + c[0]) / 1000
            startStr = f"{int(start_sec//3600):02d}:{int((start_sec%3600)//60):02d}:{start_sec%60:05.2f}"
            # Include speaker name and timestamp for DOCX export
            html.append(f'      <span class="timestamp">[{startStr}] </span>')
            html.append(f'      <span class="speaker-name">{spkr_name}: </span>')
            html.append(f'      <a href="#{startStr}" class="lt" onclick="jumptoTime({int(start_sec)})">{c[2]}</a><br>')
        html.append("    </div>")
    html.append("  </div> <!-- end of class e and speaker segments -->\n    </div> <!-- end of content -->")
    
    # Add JavaScript at the end of the body for proper DOM loading
    javascript_code = """
    <script>
      console.log('Loading video highlight script...');
      
      function jumptoTime(time){
          var v = document.getElementsByTagName('video')[0];
          console.log("jumping to time:", time);
          if (v) {
              v.currentTime = time;
          }
      }

      // Track current segment highlighting
      var currentHighlighted = null;

      function highlightCurrentSegment() {
          var v = document.getElementsByTagName('video')[0];
          if (!v) {
              console.log('Video element not found');
              return;
          }
          
          var currentTime = v.currentTime;
          console.log('Current video time:', currentTime);
          
          // Find all clickable transcript segments
          var segments = document.querySelectorAll('a.lt[onclick]');
          console.log('Found segments:', segments.length);
          
          var targetSegment = null;
          
          // Find the segment that should be highlighted based on current video time
          for (var i = 0; i < segments.length; i++) {
              var onclick = segments[i].getAttribute('onclick');
              if (!onclick) continue;
              
              var match = onclick.match(/jumptoTime\\((\\d+)\\)/);
              if (!match) continue;
              
              var segmentTime = parseInt(match[1]);
              
              // Check if this is the current or most recent segment
              if (segmentTime <= currentTime) {
                  targetSegment = segments[i];
              } else {
                  break; // segments are in chronological order
              }
          }
          
          // Only update highlighting if we're switching to a different segment
          if (targetSegment !== currentHighlighted) {
              // Remove previous highlighting
              if (currentHighlighted) {
                  currentHighlighted.style.backgroundColor = '';
                  currentHighlighted.style.fontWeight = '';
                  console.log('Removed previous highlight');
              }
              
              // Highlight new segment
              if (targetSegment) {
                  targetSegment.style.backgroundColor = '#ffeb3b';
                  targetSegment.style.fontWeight = 'bold';
                  currentHighlighted = targetSegment;
                  console.log('Highlighted new segment:', targetSegment.textContent.substring(0, 50) + '...');
                  
                  // Scroll to keep current segment visible
                  targetSegment.scrollIntoView({
                      behavior: 'smooth',
                      block: 'center'
                  });
              }
          }
      }

      // Initialize when DOM is ready
      function initializeVideoTracking() {
          console.log('Initializing video tracking...');
          var v = document.getElementsByTagName('video')[0];
          if (v) {
              console.log('Video found, adding event listeners');
              // Update highlighting as video plays
              v.addEventListener('timeupdate', highlightCurrentSegment);
              
              // Also update when user seeks
              v.addEventListener('seeked', highlightCurrentSegment);
              
              // Initial highlight check
              setTimeout(highlightCurrentSegment, 100);
          } else {
              console.log('Video not found, retrying in 500ms');
              setTimeout(initializeVideoTracking, 500);
          }
      }
      
      // Start initialization when DOM loads
      if (document.readyState === 'loading') {
          document.addEventListener('DOMContentLoaded', initializeVideoTracking);
      } else {
          initializeVideoTracking();
      }
    </script>
  </body>
</html>"""
    
    html.append(javascript_code)
    with open(outputHtml, "w", encoding="utf-8") as f:
        f.write("\n".join(html))
    

def cleanup(files):
    for f in files:
        if os.path.isfile(f):
            os.remove(f)

def transcribe_video(inputfile, speaker_names=None):
    basename = Path(inputfile).stem
    workdir = basename
    Path(workdir).mkdir(exist_ok=True)
    os.chdir(workdir)

    # Prepare audio
    inputWavCache = f"{basename}.cache.wav"
    convert_to_wav(f"../{inputfile}", inputWavCache)
    outputWav = f"{basename}-spaced.wav"
    create_spaced_audio(inputWavCache, outputWav)

    diarizationFile = f"{basename}-diarization.txt"
    dzs = get_diarization(outputWav, diarizationFile)
    groups = group_segments(dzs)

    segment_files = export_segments_audio(groups, outputWav)
    vtt_files = transcribe_segments(segment_files)

    # Setup speakers mapping
    speakers = {}
    if speaker_names:
        for i, name in enumerate(speaker_names):
            speakers[f"SPEAKER_{i:02d}"] = (name, 'lightgray', 'darkorange')
    else:
        speakers = {
            'SPEAKER_00': ('Speaker 1', 'lightgray', 'darkorange'),
            'SPEAKER_01': ('Speaker 2', '#e1ffc7', 'darkgreen'),
            'SPEAKER_02': ('Speaker 3', '#e1ffc7', 'darkblue'),
        }

    generate_html(f"../{basename}.html", groups, vtt_files, inputfile, speakers)
    cleanup([inputWavCache, outputWav] + segment_files)
    print(f"Script completed successfully! Output: ../{basename}.html")

def main():
    if len(sys.argv) < 2:
        print("Usage: whisper-transcribe <video_file> [speaker_names...]")
        sys.exit(1)

    inputfile = sys.argv[1]
    speaker_names = sys.argv[2:]  # any extra args are speaker names

    # Default speaker labels
    default_speakers = ["Speaker 1", "Speaker 2", "Speaker 3", "Speaker 4", "Speaker 5", "Speaker 6"]

    # If user provides names, override defaults
    for i, name in enumerate(speaker_names):
        if i < len(default_speakers):
            default_speakers[i] = name
    transcribe_video(inputfile, default_speakers)    


if __name__ == "__main__":
    main()
