## QtDragon_hd
### Requires linuxcnc version 2.10 (master)

### Extra libraries are required in addition to those for the installation of QTVCP for additional functionality

#### For viewing job setup sheets and help pages formatted in HTML
sudo apt-get install python3-pyqt5.qtwebengine  

#### To create Z level height maps when using Z level compensation
sudo apt-get install python3-numpy  
sudo apt-get install python3-scipy  
sudo apt-get install python3-matplotlib  

#### To view PDF files
sudo apt-get install python3-poppler-qt5  

#### To enable tool database functions
sudo apt-get install python3-PyQt5.QtSql  
sudo apt-get install sqlite3 libsqlite3-dev  
You may also want a SQLITE browser such as DB Browser for Sqlite3  
sudo apt-get install sqlitebrowser  
