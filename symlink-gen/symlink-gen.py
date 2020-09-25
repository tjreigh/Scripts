import os
import tkinter as tk
from tkinter import filedialog

class Application(tk.Frame):
	def __init__(self, master=None):
			super().__init__(master)
			self.master = master
			self.pack()
			self.draw()
			self.filename = ""
			self.destination = ""

	def draw(self):
			self.fileBtn = tk.Button(self)
			self.fileBtn["text"] = "File to link"
			self.fileBtn["command"] = self.openFileDialog
			self.fileBtn.pack(side="top")

			self.saveBtn = tk.Button(self)
			self.saveBtn["text"] = "Link destination"
			self.saveBtn["command"] = self.openSaveDialog
			self.saveBtn.pack(side="top")

			self.runBtn = tk.Button(self)
			self.runBtn["text"] = "Create link"
			self.runBtn["command"] = self.makeLink
			self.runBtn.pack(side="top")

			self.quit = tk.Button(self, text="QUIT", fg="red",
														command=self.master.destroy)
			self.quit.pack(side="bottom")

	def openFileDialog(self):
		self.filename = filedialog.askopenfilename(initialdir = "/",title = "Select file")

	def openSaveDialog(self):
			self.destination = filedialog.asksaveasfilename(initialdir = "/",title = "Select file")

	def makeLink(self):
		cmdStr = "mklink \"" + self.destination + "\" \"" + self.filename + "\""
		cmdStr = cmdStr.replace("/", "\\")
		print(cmdStr)
		os.system("cmd /k " + cmdStr)

root = tk.Tk()
app = Application(master=root)
app.mainloop()