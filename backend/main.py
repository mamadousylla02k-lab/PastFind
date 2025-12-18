from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import yt_dlp
from shazamio import Shazam
import os
import asyncio
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Configuration CORS pour permettre les requêtes depuis le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En prod, spécifier les domaines exacts
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class VideoURL(BaseModel):
    url: str

@app.post("/identify")
async def identify_song(data: VideoURL):
    filename = "temp_audio.mp3"
    
    # Configuration spécifique pour TikTok
    if "tiktok.com" in data.url:
        # Simulation délai humain
        await asyncio.sleep(2)
        
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best', # Parfois forcer l'audio seul échoue sur TikTok
            'outtmpl': 'temp_audio.%(ext)s',
            'noplaylist': True,
            'quiet': True,
            'no_check_certificate': True,
            'add_header': [
                'User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36',
                'Accept:text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language:en-US,en;q=0.9',
                'Range:bytes=0-'
            ],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
    else:
        # Options standard pour les autres plateformes
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': 'temp_audio.%(ext)s',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'nocheckcertificate': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([data.url])
        
        # Le postprocessor FFmpegExtractAudio devrait créer temp_audio.mp3
        # Mais on vérifie au cas où yt-dlp aurait laissé le fichier original
        expected_filename = "temp_audio.mp3"
        
        # Si le fichier mp3 n'existe pas, vérifier les autres extensions possibles (webm, m4a, etc)
        if not os.path.exists(expected_filename):
            for ext in ['.webm', '.m4a', '.mp4', '.mkv']:
                temp_file = f"temp_audio{ext}"
                if os.path.exists(temp_file):
                    # On renomme ou convertit... mais ici le postprocessor devrait avoir fait le job.
                    # Si on est ici, c'est que le postprocessor a peut-être échoué ou n'a pas run.
                    # Pour simplicité, et vu la conf, on assume que si le download a marché, un fichier existe.
                    # On va juste essayer de le shazam tel quel si c'est de l'audio, ou le code va fail plus bas.
                    pass
        
        filename = expected_filename # On cible le mp3 final

        if not os.path.exists(filename):
            raise HTTPException(status_code=400, detail="Échec du téléchargement. TikTok bloque peut-être la requête.")

        shazam = Shazam()
        out = await shazam.recognize_song(filename)
        
        if os.path.exists(filename):
            os.remove(filename)

        if not out or not out.get('track'):
            return {"error": "Musique non trouvée"}

        track = out['track']
        
        # Extraction intelligente des liens
        return {
            "title": track.get('title'),
            "subtitle": track.get('subtitle'),
            "image": track.get('images', {}).get('coverarthq'),
            "apple_music": track.get('hub', {}).get('options', [{}])[0].get('actions', [{}])[-1].get('uri'),
            "youtube_url": f"https://www.youtube.com/results?search_query={track.get('subtitle')}+{track.get('title')}",
            "spotify_url": f"https://open.spotify.com/search/{track.get('subtitle')} {track.get('title')}"
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        if os.path.exists(filename): os.remove(filename)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)