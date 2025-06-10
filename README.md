# YouTube Video Uploader

## Purpose
This app automates the process of preparing and uploading videos to YouTube. It processes video files—optionally adding translations or other enhancements—and then uploads them directly to a YouTube channel, streamlining the workflow for content creators.

## How It Was Created
This project was developed using a "vibe coding" approach: the codebase was built iteratively and organically, focusing on rapid prototyping, experimentation, and creative exploration rather than following a rigid plan. This allowed for flexibility, quick adaptation to new ideas, and a focus on delivering a working solution efficiently.

---

## How to Use the Application

The main entry point for working with this app is `app.py`, which launches a graphical user interface (GUI) for processing and uploading videos. Here’s how the workflow typically goes:

### 1. Launch the App
Run `app.py` to start the GUI. Make sure you have Python and all required dependencies installed. The app requires FFmpeg to be available in your system PATH and a valid `client_secret.json` for YouTube uploads.

### 2. Select Input Files
- **Video File**: Choose the main video file to process.
- **Audio Files**: Optionally, provide Hebrew, Russian, and English audio tracks for translation or dubbing.

### 3. Configure Output
- **Placeholder Values**: Set the date and location, which will be used in video titles and descriptions.
- **Meeting Type**: Select the type of meeting (e.g., Sermon, Worship meeting, Prayer meeting) to adjust templates for titles and descriptions.
- **Segments**: Define specific segments for translation (optional). The format is "start-end", where start and end are in seconds. During those segments the Hebrew audio will be ducked, and the translation audio will be played at full volume.
- **Titles & Descriptions**: Customize or use default templates for each language output.

### 4. Connect to YouTube
In the Settings tab, connect your YouTube account. The app will use OAuth to authenticate and enable uploading.

### 5. Process and/or Upload
- **Process Videos Only**: Processes the videos and saves them locally.
- **Process & Upload**: Processes and uploads the videos directly to YouTube.
- **Upload Existing Videos**: Uploads previously processed videos.
- **Cancel Operation**: Stops any ongoing processing or upload.

### 6. Monitor Progress
Use the Logs tab to see real-time updates and any errors during processing or uploading.

### Notes
- The app uses a tabbed interface for Main, Logs, and Settings.
- All operations are performed in background threads for responsiveness.
- Tooltips and status indicators help guide the user through required steps.

If you have any questions or want to contribute, feel free to open an issue or submit a pull request!
