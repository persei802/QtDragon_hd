## QtDragon_hd
### Requires linuxcnc version 2.10 (master)

### Extra libraries are required in addition to those for the installation of QTVCP for additional functionality
sudo apt install python3-zmq
sudo apt install python3-pyqtgraph

#### For viewing job setup sheets and help pages formatted in HTML
sudo apt install python3-pyqt5.qtwebengine  

#### To create Z level height maps when using Z level compensation
sudo apt install python3-numpy  
sudo apt install python3-scipy  

#### To view PDF files
sudo apt install python3-poppler-qt5  

#### To enable tool database functions
sudo apt install python3-PyQt5.QtSql  
sudo apt install sqlite3 libsqlite3-dev  
You may also want a SQLITE browser such as DB Browser for Sqlite3  
sudo apt install sqlitebrowser  

## To Copy QtDragon to Local Machine
#### If git not installed:
sudo apt install git
#### Create a folder to copy files to. Should be in ~/linuxcnc/configs/<folder_name>
#### Copy files to new folder
git clone https://github.com/persei802/QtDragon_hd <folder_name>
#### These are simulation files. To run on hardware, replace .hal and .ini files with hardware files.
