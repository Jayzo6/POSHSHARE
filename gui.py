import os
import re
import sys
import time
import queue
import threading
import random
from typing import List, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
	from poshshare.models import ClosetTarget, parse_closets_lines, format_closets_lines
	from poshshare.automation import Sharer
	from poshshare.app_paths import get_closets_path, get_credentials_path
except ImportError:
	from models import ClosetTarget, parse_closets_lines, format_closets_lines
	from automation import Sharer
	from app_paths import get_closets_path, get_credentials_path


class App:
	def __init__(self, root: tk.Tk):
		self.root = root
		root.title("Poshmark Sharing Bot")

		# state
		self.log_q = queue.Queue()
		self.twofa_q = queue.Queue()  # Queue for 2FA prompts from worker threads
		self.stop_event = threading.Event()
		self.worker: Optional[threading.Thread] = None
		self.follow_worker: Optional[threading.Thread] = None  # New follower worker
		self.targets: List[ClosetTarget] = []
		self.closets_file_path = get_closets_path()

		# top frame: creds + options
		top = ttk.Frame(root, padding=10)
		top.grid(row=0, column=0, sticky="ew")
		top.columnconfigure(1, weight=1)
		top.columnconfigure(3, weight=1)

		self.var_user = tk.StringVar(value=os.environ.get("POSH_USER", ""))
		self.var_pass = tk.StringVar(value=os.environ.get("POSH_PASS", ""))
		self.var_party = tk.StringVar(value="")
		self.var_default_max = tk.IntVar(value=40)
		self.var_headful = tk.BooleanVar(value=False)
		self.var_shuffle = tk.BooleanVar(value=True)
		self.var_remember = tk.BooleanVar(value=False)
		self.var_total_shares_limit = tk.StringVar(value="")  # New setting for total shares limit
		self.var_2captcha_api_key = tk.StringVar(value=os.environ.get("2CAPTCHA_API_KEY", ""))

		# Follower variables
		self.var_follow_men = tk.BooleanVar(value=True)
		self.var_follow_women = tk.BooleanVar(value=True)
		self.var_follow_count = tk.IntVar(value=10)
		self.var_follow_jitter_min = tk.IntVar(value=3)
		self.var_follow_jitter_max = tk.IntVar(value=8)
		self.var_follow_delay = tk.IntVar(value=2)

		# Load saved credentials if they exist
		self.load_saved_credentials()
		
		# Load saved closets list if it exists
		# self.load_saved_closets()  # Moved to after tree is created
		
		# Log app ready status
		self.log("[*] Poshmark Sharing Bot initialized")
		# if self.targets:
		# 	self.log(f"[*] Ready to process {len(self.targets)} closets")

		# Create tabbed interface
		notebook = ttk.Notebook(root)
		notebook.grid(row=1, column=0, sticky="nsew", padx=10)
		root.rowconfigure(1, weight=1)

		# Main Sharing Tab
		sharing_tab = ttk.Frame(notebook, padding=10)
		notebook.add(sharing_tab, text="Sharing")

		# Followers Tab
		followers_tab = ttk.Frame(notebook, padding=10)
		notebook.add(followers_tab, text="Followers")

		# Move existing content to sharing tab
		# Top section: credentials and options
		top_sharing = ttk.Frame(sharing_tab, padding=10)
		top_sharing.grid(row=0, column=0, sticky="ew")
		top_sharing.columnconfigure(1, weight=1)
		top_sharing.columnconfigure(3, weight=1)

		ttk.Label(top_sharing, text="Username/Email:").grid(row=0, column=0, sticky="w")
		ttk.Entry(top_sharing, textvariable=self.var_user).grid(
			row=0, column=1, sticky="ew", padx=(5, 15)
		)
		ttk.Label(top_sharing, text="Password:").grid(row=0, column=2, sticky="w")
		ttk.Entry(top_sharing, textvariable=self.var_pass, show="•").grid(
			row=0, column=3, sticky="ew"
		)

		ttk.Label(top_sharing, text="Party (optional):").grid(row=1, column=0, sticky="w")
		ttk.Entry(top_sharing, textvariable=self.var_party).grid(
			row=1, column=1, sticky="ew", padx=(5, 15)
		)
		ttk.Checkbutton(top_sharing, text="Show browser", variable=self.var_headful).grid(
			row=1, column=2, sticky="w"
		)
		ttk.Checkbutton(top_sharing, text="Shuffle closets", variable=self.var_shuffle).grid(
			row=1, column=3, sticky="w"
		)

		ttk.Label(top_sharing, text="Default Max:").grid(row=2, column=0, sticky="w")
		ttk.Spinbox(top_sharing, from_=1, to=500, textvariable=self.var_default_max, width=6).grid(
			row=2, column=1, sticky="w", padx=(5, 15)
		)
		ttk.Label(top_sharing, text="Total Shares Limit:").grid(row=3, column=0, sticky="w")
		ttk.Entry(top_sharing, textvariable=self.var_total_shares_limit, width=8).grid(
			row=3, column=1, sticky="w", padx=(5, 15)
		)
		ttk.Label(top_sharing, text="2captcha API Key:").grid(row=3, column=2, sticky="w")
		ttk.Entry(top_sharing, textvariable=self.var_2captcha_api_key, show="•", width=20).grid(
			row=3, column=3, sticky="w"
		)

		# Remember login checkbox
		ttk.Checkbutton(
			top_sharing, text="Remember Login", variable=self.var_remember, command=self.on_remember_changed
		).grid(row=4, column=2, sticky="w", padx=(15, 0))

		# middle: closets file + table
		mid = ttk.Frame(sharing_tab, padding=(10, 0, 10, 10))
		mid.grid(row=1, column=0, sticky="nsew")
		mid.columnconfigure(0, weight=1)

		btn_row = ttk.Frame(mid)
		btn_row.grid(row=0, column=0, sticky="ew", pady=(0, 5))
		# Top row buttons: actions related to pasted data
		ttk.Button(btn_row, text="Extract Usernames", command=self.extract_usernames_from_paste).pack(side="left")
		ttk.Button(btn_row, text="Clear Text", command=self.clear_paste_text).pack(side="left", padx=5)

		# Add paste data section
		paste_frame = ttk.LabelFrame(mid, text="Paste Closet Data", padding=5)
		paste_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))
		paste_frame.columnconfigure(0, weight=1)
		
		# Text area for pasting data
		self.paste_text = tk.Text(paste_frame, height=6, wrap="word")
		self.paste_text.grid(row=0, column=0, sticky="ew", padx=(0, 5))
		
		# Buttons for managing closets list
		paste_btn_frame = ttk.Frame(paste_frame)
		paste_btn_frame.grid(row=1, column=0, sticky="ew", pady=(5, 0))
		ttk.Button(paste_btn_frame, text="Add", command=self.add_target).pack(side="left")
		ttk.Button(paste_btn_frame, text="Remove", command=self.remove_selected).pack(side="left", padx=5)
		ttk.Button(paste_btn_frame, text="Clear Saved", command=self.clear_saved_closets).pack(side="left", padx=(15, 0))
		
		# Instructions label
		ttk.Label(paste_frame, text="Paste your closet data here (with @usernames), then click 'Extract Usernames'", 
				 font=("TkDefaultFont", 8), foreground="gray").grid(row=2, column=0, sticky="w", pady=(5, 0))

		self.tree = ttk.Treeview(mid, columns=("user", "max"), show="headings", height=10)
		self.tree.heading("user", text="Username")
		self.tree.heading("max", text="Max to Share")
		self.tree.column("user", width=220)
		self.tree.column("max", width=120, anchor="center")
		self.tree.grid(row=2, column=0, sticky="nsew")
		mid.rowconfigure(2, weight=1)

		# enable in-place edit of "max"
		self.tree.bind("<Double-1>", self.on_tree_double_click)

		# Load saved closets list if it exists (after tree is created)
		self.load_saved_closets()
		
		# Log final app ready status
		if self.targets:
			self.log(f"[*] Ready to process {len(self.targets)} closets")

		# bottom: controls + log
		bottom = ttk.Frame(sharing_tab, padding=10)
		bottom.grid(row=2, column=0, sticky="ew")
		ttk.Button(bottom, text="Start", command=self.start).pack(side="left")
		ttk.Button(bottom, text="Stop", command=self.stop).pack(side="left", padx=6)

		self.log_txt = tk.Text(sharing_tab, height=12, wrap="word")
		self.log_txt.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
		sharing_tab.rowconfigure(3, weight=1)

		# Add some content to the Followers tab
		ttk.Label(followers_tab, text="Auto-Follow Users", font=("TkDefaultFont", 14, "bold")).grid(row=0, column=0, pady=(0, 20), columnspan=2)
		
		# Category selection frame
		category_frame = ttk.LabelFrame(followers_tab, text="Categories to Follow", padding=10)
		category_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 15))
		
		ttk.Checkbutton(category_frame, text="Men's Category", variable=self.var_follow_men).grid(row=0, column=0, sticky="w", padx=(0, 20))
		ttk.Checkbutton(category_frame, text="Women's Category", variable=self.var_follow_women).grid(row=0, column=1, sticky="w")
		
		# Follow settings frame
		settings_frame = ttk.LabelFrame(followers_tab, text="Follow Settings", padding=10)
		settings_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 15))
		
		ttk.Label(settings_frame, text="Number of people to follow:").grid(row=0, column=0, sticky="w", padx=(0, 10))
		ttk.Spinbox(settings_frame, from_=1, to=100, textvariable=self.var_follow_count, width=8).grid(row=0, column=1, sticky="w")
		
		ttk.Label(settings_frame, text="Delay between follows (seconds):").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
		ttk.Spinbox(settings_frame, from_=1, to=30, textvariable=self.var_follow_delay, width=8).grid(row=1, column=1, sticky="w", pady=(10, 0))
		
		# Jitter settings frame
		jitter_frame = ttk.LabelFrame(followers_tab, text="Jitter Settings (Random delays)", padding=10)
		jitter_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 15))
		
		ttk.Label(jitter_frame, text="Min jitter (seconds):").grid(row=0, column=0, sticky="w", padx=(0, 10))
		ttk.Spinbox(jitter_frame, from_=1, to=10, textvariable=self.var_follow_jitter_min, width=8).grid(row=0, column=1, sticky="w")
		
		ttk.Label(jitter_frame, text="Max jitter (seconds):").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
		ttk.Spinbox(jitter_frame, from_=1, to=20, textvariable=self.var_follow_jitter_max, width=8).grid(row=1, column=1, sticky="w", pady=(10, 0))
		
		# Control buttons frame
		control_frame = ttk.Frame(followers_tab)
		control_frame.grid(row=4, column=0, columnspan=2, pady=(10, 0))
		
		ttk.Button(control_frame, text="Start Following", command=self.start_following).pack(side="left", padx=(0, 10))
		ttk.Button(control_frame, text="Stop Following", command=self.stop_following).pack(side="left")
		
		# Status and progress frame
		status_frame = ttk.LabelFrame(followers_tab, text="Status", padding=10)
		status_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(15, 0))
		
		self.follow_status_label = ttk.Label(status_frame, text="Ready to start following")
		self.follow_status_label.grid(row=0, column=0, sticky="w")
		
		self.follow_progress = ttk.Progressbar(status_frame, mode='determinate')
		self.follow_progress.grid(row=1, column=0, sticky="ew", pady=(5, 0))
		status_frame.columnconfigure(0, weight=1)

		self.after_log_pump()

	# ----- GUI helpers -----
	def log(self, msg: str):
		self.log_q.put(msg)
	
	def prompt_2fa_code(self) -> str:
		"""Prompt for 2FA code from worker thread"""
		import queue
		result_queue = queue.Queue()
		
		# Put the prompt request in the 2FA queue
		self.twofa_q.put(("prompt", result_queue))
		
		# Wait for the result
		try:
			return result_queue.get(timeout=120)  # 2 minute timeout
		except queue.Empty:
			return ""
	
	def _handle_2fa_prompt(self, prompt_data):
		"""Handle 2FA prompt in main thread"""
		try:
			action, result_queue = prompt_data
			if action == "prompt":
				# Show 2FA dialog in main thread
				from tkinter import simpledialog
				code = simpledialog.askstring(
					"Poshmark 2FA Code",
					"Enter your 2FA verification code:",
					show='*'  # Hide the input for security
				)
				result_queue.put(code.strip() if code else "")
		except Exception as e:
			self.log(f"[!] Error handling 2FA prompt: {e}")
			if len(prompt_data) > 1:
				prompt_data[1].put("")  # Send empty result on error

	def after_log_pump(self):
		try:
			while True:
				msg = self.log_q.get_nowait()
				self.log_txt.insert("end", msg + "\n")
				self.log_txt.see("end")
		except queue.Empty:
			pass
		
		# Handle 2FA prompts
		try:
			while True:
				prompt_data = self.twofa_q.get_nowait()
				self._handle_2fa_prompt(prompt_data)
		except queue.Empty:
			pass
			
		self.root.after(100, self.after_log_pump)

	def get_credentials_file_path(self):
		"""Get the path to the credentials file"""
		return get_credentials_path()

	def load_saved_credentials(self):
		"""Load saved credentials from file"""
		try:
			creds_file = self.get_credentials_file_path()
			if os.path.exists(creds_file):
				with open(creds_file, "r", encoding="utf-8") as f:
					import json

					data = json.load(f)
					if "username" in data:
						self.var_user.set(data["username"])
					if "password" in data:
						self.var_pass.set(data["password"])
					if "remember" in data:
						self.var_remember.set(data["remember"])
					if "2captcha_api_key" in data:
						self.var_2captcha_api_key.set(data["2captcha_api_key"])
		except Exception:
			# Silently fail if credentials can't be loaded
			pass

	def save_credentials(self):
		"""Save credentials to file if remember is checked"""
		try:
			creds_file = self.get_credentials_file_path()
			import json

			# Always save 2captcha API key if provided
			data = {}
			if os.path.exists(creds_file):
				with open(creds_file, "r", encoding="utf-8") as f:
					data = json.load(f)
			
			# Update 2captcha API key
			api_key = self.var_2captcha_api_key.get().strip()
			if api_key:
				data["2captcha_api_key"] = api_key
			elif "2captcha_api_key" in data:
				del data["2captcha_api_key"]
			
			if self.var_remember.get():
				data["username"] = self.var_user.get().strip()
				data["password"] = self.var_pass.get().strip()
				data["remember"] = True
				with open(creds_file, "w", encoding="utf-8") as f:
					json.dump(data, f, indent=2)
			else:
				# Remove login credentials but keep 2captcha API key
				if "username" in data:
					del data["username"]
				if "password" in data:
					del data["password"]
				if "remember" in data:
					del data["remember"]
				
				if data:  # If there's still data (like 2captcha key), save it
					with open(creds_file, "w", encoding="utf-8") as f:
						json.dump(data, f, indent=2)
				elif os.path.exists(creds_file):
					# Remove file if empty
					os.remove(creds_file)
		except Exception:
			# Silently fail if credentials can't be saved
			pass

	def on_remember_changed(self):
		"""Handle remember checkbox changes"""
		if self.var_remember.get():
			# If checked, save current credentials
			self.save_credentials()
		else:
			# If unchecked, remove saved credentials
			creds_file = self.get_credentials_file_path()
			if os.path.exists(creds_file):
				try:
					os.remove(creds_file)
				except Exception:
					pass

	def load_saved_closets(self):
		"""Load saved closets list from file"""
		try:
			self.log(f"[DEBUG] Looking for closets file at: {self.closets_file_path}")
			if os.path.exists(self.closets_file_path):
				self.log(f"[DEBUG] Found closets file, reading contents...")
				with open(self.closets_file_path, "r", encoding="utf-8") as f:
					lines = f.read().splitlines()
				self.log(f"[DEBUG] Read {len(lines)} lines from file")
				self.log(f"[DEBUG] First few lines: {lines[:3]}")
				
				self.targets = parse_closets_lines(lines, self.var_default_max.get())
				self.log(f"[DEBUG] Parsed {len(self.targets)} targets from lines")
				
				self.refresh_tree()
				self.log(f"[*] Loaded {len(self.targets)} saved closets from previous session")
				if self.targets:
					closet_names = [f"@{t.user}" for t in self.targets]
					self.log(f"[*] Saved closets: {', '.join(closet_names)}")
			else:
				self.log(f"[DEBUG] No closets file found at: {self.closets_file_path}")
				self.log("[*] No saved closets found - starting with empty list")
		except Exception as e:
			self.log(f"[!] Could not load saved closets: {e}")
			self.log("[*] Starting with empty closets list")

	def save_closets_automatically(self):
		"""Save closets list to file automatically"""
		try:
			if self.targets:
				with open(self.closets_file_path, "w", encoding="utf-8") as f:
					f.write(format_closets_lines(self.targets) + "\n")
				self.log(f"[*] Auto-saved {len(self.targets)} closets to {os.path.basename(self.closets_file_path)}")
			else:
				# If no closets, remove the file
				if os.path.exists(self.closets_file_path):
					os.remove(self.closets_file_path)
					self.log(f"[*] Removed empty closets file")
		except Exception as e:
			self.log(f"[!] Could not save closets automatically: {e}")

	def clear_saved_closets(self):
		"""Clear the saved closets list"""
		# Ask for confirmation first
		if not messagebox.askyesno("Confirm Clear", 
			"Are you sure you want to clear all closets?\n\nThis will remove all closets from the current list and delete the saved file. This action cannot be undone."):
			return
			
		try:
			# Clear the current targets list
			self.targets.clear()
			self.refresh_tree()
			
			# Remove the saved file
			if os.path.exists(self.closets_file_path):
				os.remove(self.closets_file_path)
				self.log(f"[*] Cleared saved closets file and current list")
			else:
				self.log(f"[*] Cleared current closets list (no saved file to remove)")
		except Exception as e:
			self.log(f"[!] Could not clear saved closets: {e}")

	def remove_completed_closet(self, username: str, shared_count: int = 0):
		"""Remove a completed closet from the list and save automatically"""
		try:
			# Find and remove the closet by username
			for i, target in enumerate(self.targets):
				if target.user == username:
					removed = self.targets.pop(i)
					if shared_count > 0:
						self.log(f"[✓] Completed and removed closet: @{removed.user} ({shared_count} items shared)")
					else:
						self.log(f"[✓] Removed closet: @{removed.user} (no shareable items found)")
					self.refresh_tree()
					# Save the updated list automatically
					self.save_closets_automatically()
					return True
			
			# If we get here, the closet wasn't found (might have been removed already)
			self.log(f"[!] Closet @{username} not found in list (may have been removed already)")
			return False
		except Exception as e:
			self.log(f"[!] Error removing completed closet @{username}: {e}")
			return False

	def load_file(self):
		path = filedialog.askopenfilename(
			title="Open closets file", filetypes=[("Text", "*.txt"), ("All", "*.*")]
		)
		if not path:
			return
		try:
			with open(path, "r", encoding="utf-8") as f:
				lines = f.read().splitlines()
		except Exception as e:
			messagebox.showerror("Error", f"Failed to read file:\n{e}")
			return
		self.targets = parse_closets_lines(lines, self.var_default_max.get())
		self.refresh_tree()
		self.log(f"Loaded {len(self.targets)} closets from {os.path.basename(path)}")
		# Save the loaded closets to the automatic save file
		self.save_closets_automatically()

	def save_file(self):
		if not self.targets:
			messagebox.showinfo("Nothing to save", "The list is empty.")
			return
		path = filedialog.asksaveasfilename(
			defaultextension=".txt", filetypes=[("Text", "*.txt")]
		)
		if not path:
			return
		try:
			with open(path, "w", encoding="utf-8") as f:
				f.write(format_closets_lines(self.targets) + "\n")
		except Exception as e:
			messagebox.showerror("Error", f"Failed to save file:\n{e}")
			return
		self.log(f"Saved closets to {os.path.basename(path)}")

	def extract_usernames_from_paste(self):
		"""Extract usernames from pasted data and add them to the targets list"""
		try:
			# Get the text from the paste area
			pasted_text = self.paste_text.get("1.0", tk.END).strip()
			if not pasted_text:
				messagebox.showinfo("No Data", "Please paste some data first.")
				return
			
			# Debug: Log the pasted text
			self.log(f"[DEBUG] Pasted text length: {len(pasted_text)} characters")
			self.log(f"[DEBUG] First 200 chars: {pasted_text[:200]}...")
			
			# Extract usernames (everything after @ symbol)
			import re
			username_pattern = r'@([A-Za-z0-9_.-]+)'
			usernames = re.findall(username_pattern, pasted_text)
			
			# Debug: Log found usernames
			self.log(f"[DEBUG] Found {len(usernames)} usernames: {usernames[:5]}...")
			
			if not usernames:
				messagebox.showinfo("No Usernames Found", "No usernames (starting with @) were found in the pasted data.")
				return
			
			# Check for duplicates and existing usernames
			new_usernames = []
			existing_usernames = {target.user for target in self.targets}
			
			# Debug: Log existing usernames
			self.log(f"[DEBUG] Current list has {len(existing_usernames)} existing usernames")
			
			for username in usernames:
				if username not in existing_usernames and username not in new_usernames:
					new_usernames.append(username)
			
			# Debug: Log new usernames
			self.log(f"[DEBUG] {len(new_usernames)} usernames are new (not duplicates)")
			
			if not new_usernames:
				messagebox.showinfo("No New Usernames", "All usernames are already in your list or were duplicates.")
				return
			
			# Add new usernames to targets
			added_count = 0
			for username in new_usernames:
				self.targets.append(
					ClosetTarget(user=username, max_items=self.var_default_max.get())
				)
				added_count += 1
			
			# Debug: Log final state
			self.log(f"[DEBUG] After adding, targets list has {len(self.targets)} items")
			
			# Update the GUI and save
			self.refresh_tree()
			self.save_closets_automatically()
			
			# Debug: Log tree state
			tree_items = len(self.tree.get_children())
			self.log(f"[DEBUG] Tree now shows {tree_items} items")
			
			# Show results
			if added_count == len(usernames):
				self.log(f"[✓] Added {added_count} new closets from pasted data")
			else:
				self.log(f"[✓] Added {added_count} new closets (skipped {len(usernames) - added_count} duplicates/existing)")
			
			# Clear the paste text area
			self.paste_text.delete("1.0", tk.END)
			
		except Exception as e:
			self.log(f"[!] Error extracting usernames: {e}")
			messagebox.showerror("Error", f"Failed to extract usernames:\n{e}")

	def clear_paste_text(self):
		"""Clear the paste text area"""
		self.paste_text.delete("1.0", tk.END)

	def refresh_tree(self):
		for i in self.tree.get_children():
			self.tree.delete(i)
		for t in self.targets:
			self.tree.insert("", "end", values=(t.user, t.max_items))

	def add_target(self):
		self.targets.append(
			ClosetTarget(user="username", max_items=self.var_default_max.get())
		)
		self.refresh_tree()
		self.save_closets_automatically()

	def remove_selected(self):
		sel = self.tree.selection()
		if not sel:
			return
		indices = sorted([self.tree.index(i) for i in sel], reverse=True)
		for idx in indices:
			if 0 <= idx < len(self.targets):
				self.targets.pop(idx)
		self.refresh_tree()
		self.save_closets_automatically()

	def on_tree_double_click(self, event):
		# allow editing "max" or username by double-click
		item_id = self.tree.identify_row(event.y)
		col = self.tree.identify_column(event.x)
		if not item_id:
			return
		idx = self.tree.index(item_id)
		if not (0 <= idx < len(self.targets)):
			return
		x, y, w, h = self.tree.bbox(item_id, col)
		edit = tk.Entry(self.tree)
		current = self.tree.set(item_id, "max" if col == "#2" else "user")
		edit.insert(0, current)
		edit.place(x=x, y=y, width=w, height=h)
		edit.focus_set()

		def commit(e=None):
			val = edit.get().strip()
			edit.destroy()
			if col == "#2":  # max
				try:
					self.targets[idx].max_items = max(1, int(val))
				except Exception:
					return
			else:  # user
				if re.match(r"^[A-Za-z0-9_.-]+$", val):
					self.targets[idx].user = val
			self.refresh_tree()
			self.save_closets_automatically()

		edit.bind("<Return>", commit)
		edit.bind("<FocusOut>", commit)

	# ----- run/stop -----
	def start(self):
		if self.worker and self.worker.is_alive():
			messagebox.showinfo("Running", "Bot is already running.")
			return

		# validate credentials
		user = self.var_user.get().strip()
		pw = self.var_pass.get().strip()
		if not user or not pw:
			messagebox.showerror(
				"Missing credentials",
				"Enter Username/Email and Password (or set POSH_USER/POSH_PASS).",
			)
			return

		# build targets
		if not self.targets:
			messagebox.showinfo("No closets", "Load or add at least one closet.")
			return

		tlist = list(self.targets)
		if self.var_shuffle.get():
			random.shuffle(tlist)

		# Save credentials if remember is checked
		if self.var_remember.get():
			self.save_credentials()

		# Save 2captcha API key if provided
		api_key = self.var_2captcha_api_key.get().strip()
		if api_key:
			self.save_credentials()  # Save API key
		
		# start worker
		self.stop_event.clear()
		self.worker = threading.Thread(
			target=self._run_worker,
			args=(
				user,
				pw,
				tlist,
				self.var_party.get().strip(),
				self.var_headful.get(),
				0,  # slowmo disabled in UI; always 0
				self.var_total_shares_limit.get().strip(),  # Pass total shares limit
				api_key,  # Pass 2captcha API key
			),
		)
		self.worker.daemon = True
		self.worker.start()
		self.log(f"[*] Bot started with {len(tlist)} closets to process.")

	def _run_worker(
		self, user: str, pw: str, targets: List[ClosetTarget], party: str, headful: bool, slowmo: int, total_shares_limit: str, twocaptcha_api_key: str = ""
	):
		try:
			sharer = Sharer(self.log, self.stop_event, on_closet_completed=self.remove_completed_closet, twofa_callback=self.prompt_2fa_code)
			sharer.run(user, pw, targets, party, headful, slowmo, total_shares_limit, twocaptcha_api_key)
		except Exception as e:
			self.log(f"[!] Worker error: {e}")

	def stop(self):
		if not self.worker or not self.worker.is_alive():
			messagebox.showinfo("Not running", "Bot is not running.")
			return
		self.stop_event.set()
		self.log("[*] Stop requested. Waiting for current operation...")
		if self.worker:
			self.worker.join(timeout=5.0)
		self.log(f"[*] Bot stopped. {len(self.targets)} closets remaining in list.")

	# ----- Follower methods -----
	def start_following(self):
		"""Start the auto-following process"""
		if self.follow_worker and self.follow_worker.is_alive():
			messagebox.showinfo("Running", "Follower bot is already running.")
			return

		# Validate credentials
		user = self.var_user.get().strip()
		pw = self.var_pass.get().strip()
		if not user or not pw:
			messagebox.showerror(
				"Missing credentials",
				"Enter Username/Email and Password in the Sharing tab first.",
			)
			return

		# Validate category selection
		if not self.var_follow_men.get() and not self.var_follow_women.get():
			messagebox.showerror(
				"No Categories Selected",
				"Please select at least one category (Men's or Women's) to follow from.",
			)
			return

		# Validate follow count
		follow_count = self.var_follow_count.get()
		if follow_count < 1:
			messagebox.showerror("Invalid Count", "Please enter a valid number of people to follow.")
			return

		# Validate jitter settings
		jitter_min = self.var_follow_jitter_min.get()
		jitter_max = self.var_follow_jitter_max.get()
		if jitter_min > jitter_max:
			messagebox.showerror("Invalid Jitter", "Minimum jitter cannot be greater than maximum jitter.")
			return

		# Save credentials if remember is checked
		if self.var_remember.get():
			self.save_credentials()

		# Start follower worker
		self.stop_event.clear()
		self.follow_worker = threading.Thread(
			target=self._run_follow_worker,
			args=(
				user,
				pw,
				self.var_follow_men.get(),
				self.var_follow_women.get(),
				follow_count,
				self.var_follow_delay.get(),
				jitter_min,
				jitter_max,
			),
		)
		self.follow_worker.daemon = True
		self.follow_worker.start()
		
		# Update UI
		self.follow_status_label.config(text="Following in progress...")
		self.follow_progress.config(maximum=follow_count, value=0)
		self.log(f"[*] Follower bot started - will follow {follow_count} people")

	def stop_following(self):
		"""Stop the auto-following process"""
		if not self.follow_worker or not self.follow_worker.is_alive():
			messagebox.showinfo("Not running", "Follower bot is not running.")
			return
		
		self.stop_event.set()
		self.log("[*] Stop requested for follower bot. Waiting for current operation...")
		if self.follow_worker:
			self.follow_worker.join(timeout=5.0)
		self.follow_status_label.config(text="Following stopped")
		self.log("[*] Follower bot stopped")

	def _run_follow_worker(
		self, user: str, pw: str, follow_men: bool, follow_women: bool, 
		follow_count: int, base_delay: int, jitter_min: int, jitter_max: int
	):
		"""Worker thread for following users"""
		try:
			from browser_manager import BrowserManager
			from login_handler import LoginHandler
			
			# Initialize components
			login_handler = LoginHandler(self.log, self.prompt_2fa_code)
			
			# Use browser manager for clean browser handling
			with BrowserManager(headful=not self.var_headful.get(), slowmo_ms=0) as page:
				# Attempt to login
				if not login_handler.login(page, user, pw):
					self.log("[!] Login failed! Stopping follower bot.")
					return

				self.log("[*] Login successful, proceeding with following...")
				
				# Determine which categories to process
				categories = []
				if follow_men:
					categories.append(("Men", "https://poshmark.com/category/Men"))
				if follow_women:
					categories.append(("Women", "https://poshmark.com/category/Women"))
				
				followed_count = 0
				category_index = 0
				batch_size = 20  # Collect 20 usernames per category before following
				
				while followed_count < follow_count and not self.stop_event.is_set():
					# Get current category
					category_name, category_url = categories[category_index % len(categories)]
					
					try:
						self.log(f"[*] Collecting usernames from {category_name}'s category...")
						
						# Navigate to category page
						page.goto(category_url)
						page.wait_for_load_state("networkidle")
						time.sleep(2)  # Additional wait for dynamic content
						
						# Find usernames using the selector pattern
						# The selector targets the username links in the listing tiles
						username_elements = page.query_selector_all("div.tiles_container div div div.d--fl.ai--c.jc--sb a")
						
						if username_elements:
							# Extract usernames first (don't follow yet)
							usernames_to_follow = []
							for element in username_elements:
								if len(usernames_to_follow) >= batch_size:
									break
								
								try:
									username = element.get_attribute("href").split("/")[-1]
									if username and username != "category" and username not in usernames_to_follow:
										usernames_to_follow.append(username)
								except Exception as e:
									self.log(f"[!] Error extracting username: {e}")
									continue
							
							self.log(f"[*] Collected {len(usernames_to_follow)} usernames from {category_name}'s category")
							
							# Now follow all collected usernames
							successful_follows_in_batch = 0
							for username in usernames_to_follow:
								if self.stop_event.is_set() or followed_count >= follow_count:
									break
								
								try:
									# Navigate to user profile and follow
									profile_url = f"https://poshmark.com/closet/{username}"
									page.goto(profile_url)
									page.wait_for_load_state("networkidle")
									time.sleep(1)  # Brief wait for page elements
									
									# Look for follow button - try multiple selectors
									follow_button = None
									try:
										# Try data-testid first
										follow_button = page.query_selector("button[data-testid='follow-button']")
									except:
										pass
									
									if not follow_button:
										try:
											# Try finding button with "Follow" text
											follow_button = page.query_selector("button:has-text('Follow')")
										except:
											pass
									
									if not follow_button:
										try:
											# Try finding any button containing "Follow"
											follow_button = page.query_selector("button")
											if follow_button and "Follow" in follow_button.text_content():
												pass  # Keep this button
											else:
												follow_button = None
										except:
											pass
									
									if follow_button and "Follow" in follow_button.text_content():
										follow_button.click()
										followed_count += 1
										successful_follows_in_batch += 1
										
										# Update progress
										self.follow_progress.config(value=followed_count)
										self.follow_status_label.config(
											text=f"Followed {followed_count}/{follow_count} users (Current: {category_name} batch)"
										)
										
										self.log(f"[✓] Followed @{username} ({followed_count}/{follow_count}) - {category_name} batch")
										
										# Apply jitter delay
										jitter = random.uniform(jitter_min, jitter_max)
										time.sleep(base_delay + jitter)
									else:
										self.log(f"[!] Follow button not found for @{username} (likely already following)")
										
								except Exception as e:
									self.log(f"[!] Error following @{username}: {e}")
									continue
							
							# Check if we need to get new usernames (if most were already followed)
							follow_rate = successful_follows_in_batch / len(usernames_to_follow) if usernames_to_follow else 0
							
							# If follow rate is low (less than 30%), refresh the category page for new usernames
							if follow_rate < 0.3 and len(usernames_to_follow) > 0:
								self.log(f"[*] Low follow rate ({follow_rate:.1%}) - refreshing {category_name} category for new usernames...")
								continue  # Go back to category page collection
							
							# Switch to next category after completing batch
							if len(categories) > 1 and followed_count < follow_count:
								category_index += 1
								self.log(f"[*] Completed batch of {len(usernames_to_follow)} follows on {category_name}. Switching to {categories[category_index % len(categories)][0]} category...")
							else:
								# If only one category or done, stay on current category
								if followed_count < follow_count:
									self.log(f"[*] Completed batch on {category_name}. Starting new batch...")
						
						else:
							self.log(f"[!] No username elements found on {category_name} category page")
							# Try next category
							category_index += 1
						
					except Exception as e:
						self.log(f"[!] Error processing {category_name} category: {e}")
						# Try next category
						category_index += 1
						continue
				
				# Final status update
				if followed_count >= follow_count:
					self.follow_status_label.config(text=f"Completed! Followed {followed_count} users")
					self.log(f"[✓] Follower bot completed - followed {followed_count} users")
				else:
					self.follow_status_label.config(text="Following stopped by user")
					self.log(f"[*] Follower bot stopped - followed {followed_count} users")
			
		except Exception as e:
			self.log(f"[!] Follower worker error: {e}")
			self.follow_status_label.config(text="Error occurred")
		finally:
			self.follow_worker = None


def main():
	root = tk.Tk()
	app = App(root)
	root.mainloop()
