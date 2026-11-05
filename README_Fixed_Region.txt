SmartScreen Capture & Recording V1.0 (internal update build 1.0.1)

NEW: Video Recording > Area > Full Screen or Custom Region.

CUSTOM REGION:
1. Choose Custom Region.
2. Click Select Area. SmartScreen hides; drag a rectangle over the desired HMI.
3. Press Enter to confirm, or Escape to cancel. The area is saved to config.json beside SmartScreen_Capture.exe.
4. Click Show Area to highlight the saved rectangle for 1.6 seconds (only when NOT recording).
5. Start Recording. The recorder captures ONLY the chosen rectangle. A black background preserves the selected output aspect ratio at 720p/1080p.
6. Change to Full Screen to return to normal recording.

Notes:
- The rectangle is fixed to absolute desktop coordinates, not attached to a moving window.
- If monitor layout changes, select the area again; recording rejects out-of-range coordinates.
- The region selection overlay is shown before recording, not over the recorded video.
- Screenshot behavior remains unchanged: it captures the selected monitor/full screen, not the video region.
- For software encoding, choose 720p, 10 FPS first on low-performance machines.
- No changes to FFmpeg / OpenCV fallback, 1 GB rollover, or low-disk protection.
- build via Build_cxFreeze.bat on Windows with dependencies installed.
- Auto update retained: publish Release/SmartScreen_Capture_V1_0_1 to Current with Publish_Release_To_Current.bat.
- Include the whole release folder; config.json and update_source.txt stay local to equipment PC.
- Validate on a nonproduction equipment PC before publishing to Current.
