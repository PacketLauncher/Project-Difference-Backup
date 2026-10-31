@echo off

python -m PyInstaller --onefile --windowed --clean --name "Project Difference Backup" --icon "Icon.ico" --add-data "Icon.ico;." --collect-all tkinterdnd2 "Project_Difference_Backup.py"

if exist "Project Difference Backup.exe" del "Project Difference Backup.exe"

move "dist\Project Difference Backup.exe"