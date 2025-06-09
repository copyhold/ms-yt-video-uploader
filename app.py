# app.py
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, Text, simpledialog, Frame, Canvas, Scrollbar
from tkinter import ttk
import os
import threading
import queue
import subprocess
import datetime
import traceback # For detailed error logging

from youtube_uploader import get_authenticated_service, upload_video
from ffmpeg_processor import (
    process_video_hebrew_only,
    process_video_with_translation,
    parse_segments_string
)

def create_custom_output_filename(meeting_type, lang_suffix, output_dir="output_videos", language_code=None):
    # Use current local time as per user system (2025-06-09T07:33:03+03:00)
    now = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
    mt = meeting_type.replace(" ", "_").lower() # file-safe
    if language_code is None:
        language_code = lang_suffix
    filename = f"{now}-{mt}--{language_code}.mp4"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    return os.path.join(output_dir, filename)

CLIENT_SECRETS_FILE = 'client_secret.json'

class VideoProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Sermon Video Processor & Uploader")
        self.root.geometry("850x800") # Increased height for new buttons

        # --- Initialize instance variables FIRST ---
        self.file_paths = {
            "video": tk.StringVar(),
            "audio_he": tk.StringVar(),
            "audio_ru": tk.StringVar(),
            "audio_en": tk.StringVar()
        }
        self.youtube_service = None
        self.output_dir = "output_videos"
        self.log_queue = queue.Queue()
        self.title_vars = {}
        self.desc_texts = {}
        self.segments_data = []
        
        # Operation control
        self.is_operation_running = False
        self.cancel_event = threading.Event()
        self.current_operation_thread = None # To hold reference to the running thread

        # Store paths of successfully processed videos for potential later upload
        self.processed_video_paths = {
            "HE": None,
            "RU": None,
            "EN": None
        }


        # --- Tabbed Interface ---
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # --- Main UI Structure (Scrollable Area) in first tab ---
        main_tab = Frame(self.notebook)
        self.notebook.add(main_tab, text="Main")
        main_app_frame = Frame(main_tab)
        main_app_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = Canvas(main_app_frame)
        self.scrollbar = Scrollbar(main_app_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = Frame(self.canvas)

        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

        content_frame = self.scrollable_frame # All scrollable content goes here

        # --- Logs Tab ---
        logs_tab = Frame(self.notebook)
        self.notebook.add(logs_tab, text="Logs")
        self.log_frame = tk.LabelFrame(logs_tab, text="Log", padx=10, pady=10)
        self.log_frame.pack(padx=10, pady=10, fill="both", expand=True)
        self.log_text = scrolledtext.ScrolledText(self.log_frame, wrap=tk.WORD, height=10)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state='disabled')

        # --- Settings Tab ---
        settings_tab = Frame(self.notebook)
        self.notebook.add(settings_tab, text="Settings")
        yt_frame = tk.LabelFrame(settings_tab, text="YouTube", padx=10, pady=10)
        yt_frame.pack(padx=10, pady=10, fill="x")
        self.connect_yt_button = tk.Button(yt_frame, text="Connect to YouTube", command=self.connect_youtube)
        self.connect_yt_button.pack(side=tk.LEFT, padx=5)
        self.yt_status_label = tk.Label(yt_frame, text="Not Connected", fg="red")
        self.yt_status_label.pack(side=tk.LEFT, padx=5)


        # --- Input Files ---
        file_frame = tk.LabelFrame(content_frame, text="Input Files", padx=10, pady=10)
        file_frame.pack(padx=10, pady=10, fill="x")
        self._create_file_entry(file_frame, "Video File:", "video", 0)
        self._create_file_entry(file_frame, "Hebrew Audio:", "audio_he", 1)
        self._create_file_entry(file_frame, "Russian Audio:", "audio_ru", 2)
        self._create_file_entry(file_frame, "English Audio:", "audio_en", 3)


        # --- Output Configuration (Placeholders, Segments, Titles/Descriptions) ---
        config_frame = tk.LabelFrame(content_frame, text="Output Configuration", padx=10, pady=10)
        config_frame.pack(padx=10, pady=10, fill="x")
        # Placeholder Frame
        placeholder_frame = tk.LabelFrame(config_frame, text="Placeholder Values", padx=5, pady=5)
        placeholder_frame.pack(fill="x", padx=5, pady=5)
        tk.Label(placeholder_frame, text="Date ({date}):").grid(row=0, column=0, sticky="w", pady=2)
        self.date_var = tk.StringVar(value=datetime.date.today().strftime("%Y-%m-%d"))
        tk.Entry(placeholder_frame, textvariable=self.date_var, width=40).grid(row=0, column=1, sticky="ew", pady=2)
        tk.Label(placeholder_frame, text="Location ({location}):").grid(row=1, column=0, sticky="w", pady=2)
        self.location_var = tk.StringVar(value="Church Name")
        tk.Entry(placeholder_frame, textvariable=self.location_var, width=40).grid(row=1, column=1, sticky="ew", pady=2)
        # Meeting Type Dropdown
        tk.Label(placeholder_frame, text="Meeting Type:").grid(row=2, column=0, sticky="w", pady=2)
        self.meeting_type_var = tk.StringVar(value="Sermon")
        self.meeting_type_dropdown = ttk.Combobox(placeholder_frame, textvariable=self.meeting_type_var, state="readonly", values=["Sermon", "Worship meeting", "Prayer meeting"])
        self.meeting_type_dropdown.grid(row=2, column=1, sticky="ew", pady=2)
        self.meeting_type_dropdown.bind("<<ComboboxSelected>>", self._on_meeting_type_change)
        placeholder_frame.columnconfigure(1, weight=1)
        # Segments Frame
        segments_frame = tk.LabelFrame(config_frame, text="Preaching Segments", padx=5, pady=5)
        segments_frame.pack(fill="x", padx=5, pady=5)
        self.segments_list = tk.Listbox(segments_frame, height=5, width=48)
        self.segments_list.pack(side=tk.LEFT, fill="x", expand=True, padx=5, pady=5)
        segments_scroll_y = tk.Scrollbar(segments_frame, orient="vertical", command=self.segments_list.yview)
        segments_scroll_y.pack(side=tk.LEFT, fill="y", pady=5)
        self.segments_list.config(yscrollcommand=segments_scroll_y.set)
        segments_btn_frame = tk.Frame(segments_frame)
        segments_btn_frame.pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(segments_btn_frame, text="Add", command=self.add_segment).pack(pady=2, fill="x")
        tk.Button(segments_btn_frame, text="Remove", command=self.remove_segment).pack(pady=2, fill="x")
        # Language Specific Configs
        he_config_frame = tk.LabelFrame(config_frame, text="Hebrew Output", padx=5, pady=5)
        he_config_frame.pack(fill="x", padx=5, pady=5)
        # Default templates for each meeting type and language
        self.default_templates = {
            "Sermon": {
                "HE": ("שיעור - {date}", "הקלטת השיעור מתאריך {date} ב{location}.\nצפייה מהנה!"),
                "RU": ("Проповедь ({date}) - Перевод на русский", "Запись проповеди от {date}, место: {location}.\nПеревод на русский язык."),
                "EN": ("Sermon ({date}) - English Translation", "Sermon recording from {date} at {location}.\nEnglish translation.")
            },
            "Worship meeting": {
                "HE": ("אסיפת הלל - {date}", "הקלטת אסיפת הלל מתאריך {date} ב{location}.\nצפייה מהנה!"),
                "RU": ("Прославление ({date}) - Перевод на русский", "Запись прославления от {date}, место: {location}.\nПеревод на русский язык."),
                "EN": ("Worship Meeting ({date}) - English Translation", "Worship meeting recording from {date} at {location}.\nEnglish translation.")
            },
            "Prayer meeting": {
                "HE": ("אסיפת תפילה - {date}", "הקלטת אסיפת תפילה מתאריך {date} ב{location}.\nצפייה מהנה!"),
                "RU": ("Молитвенное собрание ({date}) - Перевод на русский", "Запись молитвенного собрания от {date}, место: {location}.\nПеревод на русский язык."),
                "EN": ("Prayer Meeting ({date}) - English Translation", "Prayer meeting recording from {date} at {location}.\nEnglish translation.")
            }
        }
        self._create_title_desc_entries(he_config_frame, "HE", *self.default_templates[self.meeting_type_var.get()]["HE"])
        ru_config_frame = tk.LabelFrame(config_frame, text="Russian Output", padx=5, pady=5)
        ru_config_frame.pack(fill="x", padx=5, pady=5)
        self._create_title_desc_entries(ru_config_frame, "RU", *self.default_templates[self.meeting_type_var.get()]["RU"])
        en_config_frame = tk.LabelFrame(config_frame, text="English Output", padx=5, pady=5)
        en_config_frame.pack(fill="x", padx=5, pady=5)
        self._create_title_desc_entries(en_config_frame, "EN", *self.default_templates[self.meeting_type_var.get()]["EN"])

        # --- Action Buttons (Fixed at the bottom) ---
        action_button_frame = Frame(root) # This frame is outside the scrollable area
        action_button_frame.pack(fill="x", pady=10, padx=10)

        self.process_only_button = tk.Button(action_button_frame, text="Process Videos Only", command=self.start_process_only_thread)
        self.process_only_button.pack(side=tk.LEFT, expand=True, padx=2)

        self.process_and_upload_button = tk.Button(action_button_frame, text="Process & Upload", command=self.start_process_and_upload_thread)
        self.process_and_upload_button.pack(side=tk.LEFT, expand=True, padx=2)
        self.process_and_upload_tooltip = Tooltip(self.process_and_upload_button, "YouTube connection required to upload.")

        self.upload_existing_button = tk.Button(action_button_frame, text="Upload Existing Videos", command=self.start_upload_existing_thread)
        self.upload_existing_button.pack(side=tk.LEFT, expand=True, padx=2)
        self.upload_existing_tooltip = Tooltip(self.upload_existing_button, "YouTube connection required to upload.")

        self.cancel_button = tk.Button(action_button_frame, text="Cancel Operation", command=self.cancel_current_operation, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, expand=True, padx=2)


        # --- Log Area now handled in logs_tab above ---
        self.root.after(100, self.process_log_queue)
        self._update_button_states() # Initial button state
        self.check_input_files_present() # Initial check for enabling process buttons

    def _on_meeting_type_change(self, event=None):
        mt = self.meeting_type_var.get()
        for lang in ["HE", "RU", "EN"]:
            t, d = self.default_templates[mt][lang]
            self.title_vars[lang].set(t)
            self.desc_texts[lang].delete("1.0", tk.END)
            self.desc_texts[lang].insert(tk.END, d)

    def _on_mousewheel(self, event):
        if event.num == 4 or event.delta < 0: self.canvas.yview_scroll(1, "units")
        elif event.num == 5 or event.delta > 0: self.canvas.yview_scroll(-1, "units")

    def _create_title_desc_entries(self, parent_frame, lang_key, default_title, default_desc):
        tk.Label(parent_frame, text=f"Title ({lang_key}):").grid(row=0, column=0, sticky="w", pady=2)
        title_var = tk.StringVar(value=default_title)
        tk.Entry(parent_frame, textvariable=title_var, width=50).grid(row=0, column=1, sticky="ew", pady=2)
        self.title_vars[lang_key] = title_var
        tk.Label(parent_frame, text=f"Description ({lang_key}):").grid(row=1, column=0, sticky="nw", pady=2)
        desc_text_widget = Text(parent_frame, height=3, width=50, wrap=tk.WORD)
        desc_text_widget.insert(tk.END, default_desc)
        desc_text_widget.grid(row=1, column=1, sticky="ew", pady=2)
        self.desc_texts[lang_key] = desc_text_widget
        parent_frame.columnconfigure(1, weight=1)

    def _create_file_entry(self, parent, label_text, key, row_num):
        tk.Label(parent, text=label_text).grid(row=row_num, column=0, sticky="w", padx=5, pady=2)
        entry = tk.Entry(parent, textvariable=self.file_paths[key], width=60)
        entry.grid(row=row_num, column=1, sticky="ew", padx=5, pady=2)
        tk.Button(parent, text="Browse...", command=lambda k=key: self._browse_file(k)).grid(row=row_num, column=2, padx=5, pady=2)
        parent.columnconfigure(1, weight=1)

    def _browse_file(self, key):
        if "audio" in key: filetype = (("Audio files", "*.mp3 *.wav *.aac *.m4a"), ("All files", "*.*"))
        else: filetype = (("Video files", "*.mp4 *.mov *.avi *.mkv"), ("All files", "*.*"))
        filename = filedialog.askopenfilename(title=f"Select {key.replace('_', ' ').title()}", filetypes=filetype)
        if filename:
            self.file_paths[key].set(filename)
            self.log_message(f"Selected {key}: {filename}")
            self.check_input_files_present()

    def check_input_files_present(self):
        """Enable/disable buttons based on file selection and YouTube connection."""
        video_selected = bool(self.file_paths["video"].get())
        audio_selected = any(self.file_paths[audio_key].get() for audio_key in ["audio_he", "audio_ru", "audio_en"])
        can_process = video_selected and audio_selected
        yt_connected = self.youtube_service is not None

        if self.is_operation_running:
            return  # Don't change if an operation is active

        # Process Only: needs video and at least one audio
        if can_process:
            self.process_only_button.config(state=tk.NORMAL)
        else:
            self.process_only_button.config(state=tk.DISABLED)

        # Process & Upload: needs video, at least one audio, and YouTube connection
        if can_process and yt_connected:
            self.process_and_upload_button.config(state=tk.NORMAL)
        else:
            self.process_and_upload_button.config(state=tk.DISABLED)

        # Upload Existing: needs video, YouTube connection, and at least one processed file present
        ready_file_exists = any(
            path and os.path.isfile(path)
            for path in self.processed_video_paths.values()
        )
        if video_selected and yt_connected and ready_file_exists:
            self.upload_existing_button.config(state=tk.NORMAL)
        else:
            self.upload_existing_button.config(state=tk.DISABLED)

        self.process_and_upload_tooltip.show_if_disabled()
        self.upload_existing_tooltip.show_if_disabled()


    def connect_youtube(self):
        self.log_message("Connecting to YouTube...")
        try:
            self.youtube_service = get_authenticated_service()
            self.yt_status_label.config(text="Connected", fg="green")
            self.log_message("Successfully connected to YouTube.")
        except FileNotFoundError as e:
            self.log_message(f"ERROR: {e}")
            messagebox.showerror("YouTube Error", str(e))
            self.yt_status_label.config(text="Connection Failed (client_secret.json missing)", fg="red")
        except Exception as e:
            self.log_message(f"YouTube connection failed: {e}")
            messagebox.showerror("YouTube Error", f"Failed to connect: {e}")
            self.yt_status_label.config(text="Connection Failed", fg="red")
        # Ensure UI state is updated on the main thread
        self.root.after(0, self.check_input_files_present)


    def _update_button_states(self):
        """Enable/disable buttons based on current operation state."""
        if self.is_operation_running:
            self.process_only_button.config(state=tk.DISABLED)
            self.process_and_upload_button.config(state=tk.DISABLED)
            self.upload_existing_button.config(state=tk.DISABLED)
            self.connect_yt_button.config(state=tk.DISABLED)
            self.cancel_button.config(state=tk.NORMAL)
            self.process_and_upload_tooltip.show_if_disabled()
            self.upload_existing_tooltip.show_if_disabled()
        else:
            self.connect_yt_button.config(state=tk.NORMAL)
            self.cancel_button.config(state=tk.DISABLED)
            self.check_input_files_present() # This will correctly set process/upload buttons
            self.process_and_upload_tooltip.show_if_disabled()
            self.upload_existing_tooltip.show_if_disabled()

    def log_message(self, message): self.log_queue.put(message)

    def process_log_queue(self):
        while not self.log_queue.empty():
            try:
                message = self.log_queue.get_nowait()
                self.log_text.configure(state='normal')
                self.log_text.insert(tk.END, message + "\n")
                self.log_text.see(tk.END)
                self.log_text.configure(state='disabled')
            except queue.Empty: pass
        self.root.after(100, self.process_log_queue)

    def _get_common_data(self):
        """Collects common data for processing/uploading."""
        return {
            "video_path": self.file_paths["video"].get(),
            "he_audio_path": self.file_paths["audio_he"].get(),
            "ru_audio_path": self.file_paths["audio_ru"].get(),
            "en_audio_path": self.file_paths["audio_en"].get(),
            "date_val": self.date_var.get(),
            "location_val": self.location_var.get(),
            "segments_data": self.segments_data,
            "meeting_type": self.meeting_type_var.get(),
            "title_he_template": self.title_vars["HE"].get(),
            "desc_he_template": self.desc_texts["HE"].get("1.0", tk.END).strip(),
            "title_ru_template": self.title_vars["RU"].get(),
            "desc_ru_template": self.desc_texts["RU"].get("1.0", tk.END).strip(),
            "title_en_template": self.title_vars["EN"].get(),
            "desc_en_template": self.desc_texts["EN"].get("1.0", tk.END).strip(),
        }

    def _start_operation_thread(self, target_func, *args):
        if self.is_operation_running:
            self.log_message("An operation is already in progress.")
            return

        self.is_operation_running = True
        self.cancel_event.clear() # Reset cancel event for new operation
        self._update_button_states()
        self.log_message("Starting operation...")

        self.current_operation_thread = threading.Thread(target=target_func, args=args)
        self.current_operation_thread.daemon = True
        self.current_operation_thread.start()

        # Optionally, can add a check here to re-enable buttons if thread finishes quickly (e.g. immediate error)
        # For now, relying on the finally block in the target_func

    def start_process_only_thread(self):
        data = self._get_common_data()
        if not data["video_path"] or not data["he_audio_path"]: # Basic check
            messagebox.showerror("Input Error", "Video and Hebrew audio files are required for processing.")
            return
        self._start_operation_thread(self._perform_processing_and_or_upload, data, False) # False for perform_upload

    def start_process_and_upload_thread(self):
        data = self._get_common_data()
        if not data["video_path"] or not data["he_audio_path"]: # Basic check
            messagebox.showerror("Input Error", "Video and Hebrew audio files are required.")
            return
        if not self.youtube_service:
            messagebox.showerror("YouTube Error", "Not connected to YouTube. Please connect first.")
            return
        self._start_operation_thread(self._perform_processing_and_or_upload, data, True) # True for perform_upload

    def start_upload_existing_thread(self):
        data = self._get_common_data() # Need this for titles, descriptions, etc.
        if not data["video_path"]: # Base video name is used to find processed files
            messagebox.showerror("Input Error", "Original video file path is needed to identify files to upload.")
            return
        if not self.youtube_service:
            messagebox.showerror("YouTube Error", "Not connected to YouTube. Please connect first.")
            return
        self._start_operation_thread(self._perform_upload_existing, data)

    def cancel_current_operation(self):
        if self.is_operation_running:
            self.log_message("Cancellation request received. Will attempt to stop after current step...")
            self.cancel_event.set()
            # Note: FFmpeg processes won't be killed mid-way with this simple approach.
            # Uploads will check the event more frequently.
        else:
            self.log_message("No operation currently running to cancel.")

    def _format_with_placeholders(self, template_string, date_val, location_val):
        try: return template_string.format(date=date_val, location=location_val)
        except KeyError as e:
            self.log_message(f"Warning: Placeholder {e} in '{template_string[:50]}...'")
            return template_string

    def _operation_finished(self):
        """Called when an operation completes or is cancelled."""
        self.is_operation_running = False
        self.current_operation_thread = None
        self.root.after(0, self._update_button_states) # Ensure UI update is in main thread

    def _perform_processing_and_or_upload(self, data, perform_upload):
        """Main worker method for processing and optionally uploading."""
        try:
            video_path = data["video_path"]
            he_audio_path = data["he_audio_path"]
            ru_audio_path = data["ru_audio_path"]
            en_audio_path = data["en_audio_path"]
            date_val, location_val = data["date_val"], data["location_val"]
            meeting_type = data.get("meeting_type", "Sermon")
            segments_str = ",".join([f"{s}-{e}" for s, e in data["segments_data"]])

            # Reset processed paths for this run
            self.processed_video_paths = {"HE": None, "RU": None, "EN": None}

            # 1. Process Hebrew
            if self.cancel_event.is_set(): self.log_message("Cancelled before HE processing."); return
            self.log_message("\n--- Processing Hebrew Video ---")
            output_he_video = create_custom_output_filename(meeting_type, "he", self.output_dir, language_code="he")
            if process_video_hebrew_only(video_path, he_audio_path, output_he_video):
                self.log_message(f"Hebrew video created: {output_he_video}")
                self.processed_video_paths["HE"] = output_he_video
                if perform_upload and self.youtube_service:
                    if self.cancel_event.is_set(): self.log_message("Cancelled before HE upload."); return
                    title = self._format_with_placeholders(data["title_he_template"], date_val, location_val)
                    desc = self._format_with_placeholders(data["desc_he_template"], date_val, location_val)
                    result = upload_video(self.youtube_service, output_he_video, title, desc, cancel_event=self.cancel_event)
                    if result == "CANCELLED": self.log_message(f"Upload of '{title}' cancelled."); return
                    elif result: self.log_message(f"Uploaded '{title}' to YouTube.")
                    else: self.log_message(f"Failed to upload HE video or upload was interrupted.")
            else: self.log_message(f"Failed to process Hebrew video.")

            # 2. Process Russian
            if ru_audio_path: # Only if Russian audio is provided
                if self.cancel_event.is_set(): self.log_message("Cancelled before RU processing."); return
                self.log_message("\n--- Processing Russian Translation Video ---")
                output_ru_video = create_custom_output_filename(meeting_type, "ru", self.output_dir, language_code="ru")
                ru_segments = parse_segments_string(segments_str)
                if process_video_with_translation(video_path, he_audio_path, ru_audio_path, output_ru_video, ru_segments):
                    self.log_message(f"Russian mixed video created: {output_ru_video}")
                    self.processed_video_paths["RU"] = output_ru_video
                    if perform_upload and self.youtube_service:
                        if self.cancel_event.is_set(): self.log_message("Cancelled before RU upload."); return
                        title = self._format_with_placeholders(data["title_ru_template"], date_val, location_val)
                        desc = self._format_with_placeholders(data["desc_ru_template"], date_val, location_val)
                        result = upload_video(self.youtube_service, output_ru_video, title, desc, cancel_event=self.cancel_event)
                        if result == "CANCELLED": self.log_message(f"Upload of '{title}' cancelled."); return
                        elif result: self.log_message(f"Uploaded '{title}' to YouTube.")
                        else: self.log_message(f"Failed to upload RU video or upload was interrupted.")
                else: self.log_message(f"Failed to process Russian mixed video.")

            # 3. Process English
            if en_audio_path: # Only if English audio is provided
                if self.cancel_event.is_set(): self.log_message("Cancelled before EN processing."); return
                self.log_message("\n--- Processing English Translation Video ---")
                output_en_video = create_custom_output_filename(meeting_type, "en", self.output_dir, language_code="en")
                en_segments = parse_segments_string(segments_str)
                if process_video_with_translation(video_path, he_audio_path, en_audio_path, output_en_video, en_segments):
                    self.log_message(f"English mixed video created: {output_en_video}")
                    self.processed_video_paths["EN"] = output_en_video
                    if perform_upload and self.youtube_service:
                        if self.cancel_event.is_set(): self.log_message("Cancelled before EN upload."); return
                        title = self._format_with_placeholders(data["title_en_template"], date_val, location_val)
                        desc = self._format_with_placeholders(data["desc_en_template"], date_val, location_val)
                        result = upload_video(self.youtube_service, output_en_video, title, desc, cancel_event=self.cancel_event)
                        if result == "CANCELLED": self.log_message(f"Upload of '{title}' cancelled."); return
                        elif result: self.log_message(f"Uploaded '{title}' to YouTube.")
                        else: self.log_message(f"Failed to upload EN video or upload was interrupted.")
                else: self.log_message(f"Failed to process English mixed video.")
            
            if self.cancel_event.is_set(): self.log_message("Operation cancelled during processing/upload.")
            else: self.log_message("\n--- All tasks completed for this operation. ---")

        except Exception as e:
            self.log_message(f"FATAL ERROR in operation thread: {e}")
            self.log_message(traceback.format_exc())
        finally:
            self._operation_finished()

    def _perform_upload_existing(self, data):
        """Main worker method for uploading existing processed files."""
        try:
            date_val, location_val = data["date_val"], data["location_val"]
            meeting_type = data.get("meeting_type", "Sermon")
            
            lang_info = {
                "HE": ("he", "title_he_template", "desc_he_template"),
                "RU": ("ru", "title_ru_template", "desc_ru_template"),
                "EN": ("en", "title_en_template", "desc_en_template"),
            }

            any_uploaded = False
            for lang_key, (lang_code, title_key, desc_key) in lang_info.items():
                if self.cancel_event.is_set(): self.log_message("Upload existing cancelled."); break
                
                output_video_path = create_custom_output_filename(meeting_type, lang_code, self.output_dir, language_code=lang_code)
                # Also check self.processed_video_paths as it might have the exact path from a previous "Process Only" run
                if self.processed_video_paths.get(lang_key) and os.path.exists(self.processed_video_paths[lang_key]):
                    output_video_path = self.processed_video_paths[lang_key]
                elif not os.path.exists(output_video_path):
                    self.log_message(f"File for {lang_key} not found at {output_video_path}, skipping upload.")
                    continue

                self.log_message(f"\n--- Uploading existing {lang_key} video: {output_video_path} ---")
                title = self._format_with_placeholders(data[title_key], date_val, location_val)
                desc = self._format_with_placeholders(data[desc_key], date_val, location_val)
                
                result = upload_video(self.youtube_service, output_video_path, title, desc, cancel_event=self.cancel_event)
                if result == "CANCELLED": self.log_message(f"Upload of '{title}' cancelled."); break
                elif result: self.log_message(f"Uploaded '{title}' to YouTube."); any_uploaded = True
                else: self.log_message(f"Failed to upload '{title}' or upload was interrupted.")
            
            if not any_uploaded and not self.cancel_event.is_set():
                self.log_message("No existing processed files found to upload for the selected base video, or all uploads failed.")
            elif self.cancel_event.is_set(): self.log_message("Upload operation cancelled.")
            else: self.log_message("\n--- Existing files upload tasks completed. ---")

        except Exception as e:
            self.log_message(f"FATAL ERROR in upload existing thread: {e}")
            self.log_message(traceback.format_exc())
        finally:
            self._operation_finished()

    def add_segment(self):
        dlg = SegmentDialog(self.root)
        if dlg.result:
            start, end = dlg.result
            if start is not None and end is not None:
                self.segments_data.append((start, end))
                self.segments_list.insert(tk.END, f"{start}-{end}")

    def remove_segment(self):
        try:
            index = self.segments_list.curselection()[0]
            del self.segments_data[index]
            self.segments_list.delete(index)
        except IndexError: messagebox.showinfo("Info", "No segment selected.")


class SegmentDialog(simpledialog.Dialog):
    def __init__(self, parent, title="Enter Segment Times (seconds)"):
        self.result = None
        super().__init__(parent, title=title)

    def body(self, master):
        tk.Label(master, text="Start Time:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        tk.Label(master, text="End Time:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.start_entry = tk.Entry(master, width=10)
        self.end_entry = tk.Entry(master, width=10)
        self.start_entry.grid(row=0, column=1, padx=5, pady=2)
        self.end_entry.grid(row=1, column=1, padx=5, pady=2)
        return self.start_entry

    def apply(self):
        try:
            start_str, end_str = self.start_entry.get(), self.end_entry.get()
            if not start_str or not end_str:
                messagebox.showerror("Input Error", "Times cannot be empty.", parent=self); self.result = None; return
            start, end = float(start_str), float(end_str)
            if start < 0 or end < 0:
                messagebox.showerror("Input Error", "Times cannot be negative.", parent=self); self.result = None; return
            if start >= end:
                messagebox.showerror("Input Error", "Start time must be < end time.", parent=self); self.result = None; return
            self.result = (start, end)
        except ValueError:
            messagebox.showerror("Input Error", "Please enter numeric values.", parent=self); self.result = None


# --- Tooltip Helper ---
class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.enter)
        widget.bind("<Leave>", self.leave)

    def showtip(self):
        if self.tipwindow or self.widget['state'] == tk.NORMAL:
            return
        x, y, cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 25
        y = y + self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT, background="#ffffe0", relief=tk.SOLID, borderwidth=1, font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

    def enter(self, event=None):
        if self.widget['state'] == tk.DISABLED:
            self.showtip()

    def leave(self, event=None):
        self.hidetip()

    def show_if_disabled(self):
        # Show/hide tooltip only if button is disabled and mouse is over it
        if self.widget['state'] == tk.DISABLED:
            pass # Will show on hover
        else:
            self.hidetip()


if __name__ == "__main__":
    try: subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        messagebox.showerror("FFmpeg Error", "FFmpeg not found."); exit()
    if not os.path.exists(CLIENT_SECRETS_FILE):
         messagebox.showwarning("YouTube API Credentials", f"'{CLIENT_SECRETS_FILE}' not found. YouTube limited.")
    main_root = tk.Tk()
    app = VideoProcessorApp(main_root)
    main_root.mainloop()