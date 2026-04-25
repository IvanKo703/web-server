Comp 2322 Multi-threaded Web Server
Name: Ko Chong Yung
Student ID: 24094935D

To run the server:
1. Install Python 3.7+ (no external libraries needed).
2. Place the server.py file inside a folder named src.
3. At the WEB-SERVER level (one level above src), create a folder
   named test_files and put your HTML and image files inside it.
4. Open a terminal in the src/ folder (or anywhere) and run:
   python server.py
5. The server will start on http://127.0.0.1:8080
6. Access it via a browser or tools like curl.

Stopping the server:
Press Ctrl+C in the terminal.

Log file
All requests are logged to server.log, which is created in the
WEB-SERVER/ folder 

Configuration:
You can change HOST, PORT and file paths at the top of server.py.
The default root for serving files is ../test_files relative to src.