cd ..

pyinstaller --onefile --collect-all selenium --collect-all webdriver_manager --add-data "OrthoAProth.ico;." --icon="OrthoAProth.ico" mainProth.py

rem this command may generate a windows virus error
rem see https://stackoverflow.com/questions/77346372/pyinstaller-says-i-made-a-virus

cd Tools
