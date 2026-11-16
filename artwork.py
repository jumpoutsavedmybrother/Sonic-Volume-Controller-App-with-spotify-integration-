"""Web album-art lookup, used only when Windows provides no thumbnail for the current track.
Once you've confirmed the Windows covers work on your machine you can delete this file and its use in ui.py."""
import io
import re
import json
import urllib.request
import urllib.parse

from PIL import Image


class WebArtLookup:
    def __init__(self):
        self._track = None
        self._image = None

    def fetch(self, track_str):
        """Blocks on the network, so call it from a worker thread. Returns a PIL image or None."""
        if track_str == self._track and self._image is not None:
            return self._image
        clean_query = re.sub(r'[\(\[\{].*?[\)\]\}]', '', track_str).strip() or track_str
        encoded_q = urllib.parse.quote(clean_query)
        for api_url in [f"https://api.deezer.com/search?q={encoded_q}&limit=3", f"https://itunes.apple.com/search?term={encoded_q}&entity=song&limit=3"]:
            try:
                req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    data = json.loads(resp.read().decode())
                img_url = None
                if "deezer" in api_url and data.get('data'):
                    img_url = data['data'][0]['album'].get('cover_xl') or data['data'][0]['album'].get('cover_big')
                elif "itunes" in api_url and data.get('resultCount', 0) > 0:
                    img_url = data['results'][0]['artworkUrl100'].replace("100x100bb", "600x600bb")

                if img_url:
                    img_req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(img_req, timeout=2.0) as img_res:
                        pil_img = Image.open(io.BytesIO(img_res.read()))
                        pil_img.load()
                    self._track = track_str
                    self._image = pil_img
                    return pil_img
            except Exception:
                pass
        return None
