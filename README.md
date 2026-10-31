Project Difference Backup | Written by Gal Shemesh (PacketLauncher)

This program backs up all modified files in a modified project folder, by comparing them with their source files in an original source directory. The backup will consist of both the ORIGINAL version of these files along with their complete directory hierarchy and timestamp, and of the MODIFIEID version of them as well - this is handy for saving an offline backup copy of both source and modified versions of the files you modified in a project, WITHOUT all the rest of the project files, such as Visual Studio's cache files and folders, dependencies and leftovers that it generates when you compile for testing.


How to use:
-----------
1. Set in the "Original path" field the path of the ORIGINAL source project directory (this most likely be an extracted ZIP archive of the project source files that you downloaded from GitHub).

2. Set in the "Modified path" field the path of the MODIFIED source project directory (the one with your changes).

3. Set in the "Save results to" field the path where you wish the cleaned folder to be generated.

4. Hit "Compare and Back Up Differences" and wait for the program to finish. It will also generate a "Results.txt" summary file.


Change log:
===========
v1.0.0.0
October 31, 2026
- Initial release.


Making an EXE from the source Python scripts:

* This is for developers who wish to make adjustments to the source script for generating an EXE.

1. Install Python

2. From CMD, install:
	py -m pip install tkinterdnd2 <-- drag and drop support for the program (mandatory)
	py -m pip install pyinstaller pillow <-- for making an EXE
	py -m pip install pillow <-- for converting the PNG icon into ICO

3. To make an new icon, update/replace the Icon.png file and run the PNG_icon_to_ICO.py script from CMD.

4. To make an EXE, either run "BuildMe.bat" or run from CMD:
	python -m PyInstaller --onefile --windowed --clean --name "Project Difference Backup" --icon "Icon.ico" --add-data "Icon.ico;." --collect-all tkinterdnd2 "Project_Difference_Backup.py"
	
5. Run "Build_Leftovers_CleanUp.bat" to clean up this folder after building the EXE.
