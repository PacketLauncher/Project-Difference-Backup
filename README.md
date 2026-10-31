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
