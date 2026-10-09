from pathlib import Path
from uuid import uuid4
from PIL import Image,UnidentifiedImageError
from flask import current_app
from app.services.common import BusinessError
def upload_root(): return Path(current_app.config.get("UPLOAD_FOLDER") or (Path(current_app.static_folder)/"uploads"))
def save_image(file,folder=""):
    if not file or not file.filename: return None
    try:
        image=Image.open(file.stream)
        if image.width*image.height>24000000: raise BusinessError("Imagem muito grande.")
        image.load(); image.thumbnail((1600,1600)); image=image.convert("RGB")
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError): raise BusinessError("Envie uma imagem válida (JPEG, PNG ou WebP).")
    path=upload_root()/folder; path.mkdir(parents=True,exist_ok=True)
    name=uuid4().hex+".jpg"; image.save(path/name,"JPEG",quality=85)
    return "uploads/"+(folder+"/" if folder else "")+name
