cd ..

pyinstaller --onefile --noconsole --collect-all selenium --collect-all webdriver_manager --add-data "OrthoAProthData/OrthoAProth.ico;." --icon="OrthoAProthData/OrthoAProth.ico" mainProth.py
pyinstaller --onefile --collect-all selenium --collect-all webdriver_manager --add-data "OrthoAProthData/OrthoAProth.ico;." --icon="OrthoAProthData/OrthoAProth.ico" mainProth.py --name mainProth_console.exe

rem this command may generate a windows virus error
rem see https://stackoverflow.com/questions/77346372/pyinstaller-says-i-made-a-virus

cd Tools
