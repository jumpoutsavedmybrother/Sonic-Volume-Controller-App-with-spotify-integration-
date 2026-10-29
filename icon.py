from PIL import Image

# Load and convert the new image
img = Image.open("new_icon.png") # the name of this png correspond to the name of the icon you would like to use for the app

# Color/transparency handling before saving
if img.mode != "RGBA":
    img = img.convert("RGBA")

img.save(
    "app_icon.ico",
    format="ICO",
    sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
print("app_icon.ico updated successfully!")
