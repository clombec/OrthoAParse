from PIL import Image
# Static for now, but can be easily adapted to convert any png to ico
img = Image.open('OrthoAProth.png')
img.save('OrthoAProth.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
