from pathlib import Path
p=Path(__file__).parent/'SmartScreen_Capture_V1_0.py'
s=p.read_text()
s=s.replace('        self.root.bind(\'<Map>\', self._on_root_map, add=\'+\')', '''        self.root.bind('<Map>', self._on_root_map, add='+')
        # Startup-only Current-channel check. Never touch active recording.
        self._update_stage = None
        self._update_queued = False
        self.root.after(1800, self._start_update_check)''')
anchor='    def _update_quality_label(self):'
assert anchor in s
insert='''    def _start_update_check(self):
        """Check server once per launch, asynchronously, without blocking the GUI."""
        if self._closing or not getattr(sys, 'frozen', False):
            return
        try:
            from smart_update import check_background, install_dir
            check_background(install_dir(), lambda version, stage:
                             self._post_gui(self._update_available, version, stage))
        except Exception:
            logging.exception('Auto-update initial check failed')

    def _update_available(self, version, stage):
        if self._closing:
            return
        self._update_stage = stage
        self._set_status('Update ' + version + ' verified and ready to install')
        self._try_start_update()

    def _try_start_update(self):
        if self._closing or self._update_stage is None:
            return
        busy = (self._recording or self._screenshot_running or
                self._video_countdown_job is not None or
                (self._record_thread is not None and self._record_thread.is_alive()))
        if busy:
            # Defer until safe, rather than interrupt machine troubleshooting.
            self._set_status('Update ready — deferred until next application launch')
            return
        from smart_update import launch_external_updater, install_dir
        try:
            launch_external_updater(install_dir(), self._update_stage)
            self._set_status('Installing verified update — SmartScreen will restart')
            self._update_stage = None
            self.root.after(150, self._on_close)
        except Exception as exc:
            logging.exception('Unable to launch external updater')
            self._set_status('Auto-update postponed: ' + str(exc), error=True)

'''
s=s.replace(anchor,insert+anchor)
s=s.replace('    root = tk.Tk()\n    app = ScreenshotApp(root)\n    root.mainloop()', '''    root = tk.Tk()
    app = ScreenshotApp(root)
    # External updater needs positive GUI-startup acknowledgement for rollback.
    ack_path = os.environ.get('SMARTSCREEN_UPDATE_ACK')
    if ack_path:
        try:
            Path(ack_path).write_text('ready', encoding='utf-8')
        except Exception:
            logging.exception('Unable to acknowledge updated application startup')
    root.mainloop()''')
p.write_text(s)
print('updated app lines',len(s.splitlines()))
