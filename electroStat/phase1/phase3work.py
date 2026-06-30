from tkinter import filedialog as fd
from tkinter import Tk
from pathlib import Path
from shutil import copy2

import matplotlib.pyplot as plt
import pandas as pd


class ElectroStat:
	def __init__(self):
		# Workspace paths
		self.rootFolder = None
		self.dataFolder = None
		self.waveformFolder = None
		self.fftFolder = None
		self.scriptsFolder = None

		# Waveform information
		self.csvPath = None
		self.data = None
		self.figure = None

		# User choices
		self.graphChk = False
		self.minChk = False
		self.maxChk = False
		self.meanChk = False

	def selectWorkingDirectory(self):
		selectedDirectory = fd.askdirectory(
			title="Select ElectroStat working directory"
		)

		if selectedDirectory == "":
			print("Working directory selection cancelled.")
			return False

		self.rootFolder = Path(selectedDirectory)

		self.dataFolder = self.rootFolder / "data"
		self.waveformFolder = self.rootFolder / "waveform"
		self.fftFolder = self.rootFolder / "fft"
		self.scriptsFolder = self.rootFolder / "scripts"

		self.dataFolder.mkdir(exist_ok=True)
		self.waveformFolder.mkdir(exist_ok=True)
		self.fftFolder.mkdir(exist_ok=True)
		self.scriptsFolder.mkdir(exist_ok=True)

		self.createWorkingDirectoryScript()

		print()
		print(f"Working directory: {self.rootFolder}")
		print(f"Data folder: {self.dataFolder}")
		print(f"Waveform folder: {self.waveformFolder}")
		print(f"FFT folder: {self.fftFolder}")
		print(f"Scripts folder: {self.scriptsFolder}")
		print()

		return True

	def createWorkingDirectoryScript(self):
		scriptPath = (
			self.scriptsFolder /
			"working_directory_creator.py"
		)

		scriptLines = [
			"from tkinter import filedialog as fd",
			"from tkinter import Tk",
			"from pathlib import Path",
			"",
			"",
			"def createWorkingDirectory():",
			"\tselectedDirectory = fd.askdirectory(",
			"\t\ttitle=\"Select ElectroStat working directory\"",
			"\t)",
			"",
			"\tif selectedDirectory == \"\":",
			"\t\tprint(\"Working directory selection cancelled.\")",
			"\t\treturn False",
			"",
			"\trootFolder = Path(selectedDirectory)",
			"",
			"\tdataFolder = rootFolder / \"data\"",
			"\twaveformFolder = rootFolder / \"waveform\"",
			"\tfftFolder = rootFolder / \"fft\"",
			"\tscriptsFolder = rootFolder / \"scripts\"",
			"",
			"\tdataFolder.mkdir(exist_ok=True)",
			"\twaveformFolder.mkdir(exist_ok=True)",
			"\tfftFolder.mkdir(exist_ok=True)",
			"\tscriptsFolder.mkdir(exist_ok=True)",
			"",
			"\tprint()",
			"\tprint(f\"Working directory created at: {rootFolder}\")",
			"\tprint(f\"Data folder: {dataFolder}\")",
			"\tprint(f\"Waveform folder: {waveformFolder}\")",
			"\tprint(f\"FFT folder: {fftFolder}\")",
			"\tprint(f\"Scripts folder: {scriptsFolder}\")",
			"\tprint()",
			"",
			"\treturn True",
			"",
			"",
			"def main():",
			"\troot = Tk()",
			"\troot.withdraw()",
			"",
			"\ttry:",
			"\t\tcreateWorkingDirectory()",
			"\tfinally:",
			"\t\troot.destroy()",
			"",
			"",
			"if __name__ == \"__main__\":",
			"\tmain()"
		]

		scriptText = "\n".join(scriptLines) + "\n"

		scriptPath.write_text(
			scriptText,
			encoding="utf-8"
		)

		print(
			f"Working-directory creator saved to: "
			f"{scriptPath}"
		)

	def selectCSV(self):
		selectedFile = fd.askopenfilename(
			title="Select waveform CSV",
			filetypes=[("CSV files", "*.csv")]
		)

		if selectedFile == "":
			print("CSV selection cancelled.")
			return False

		sourcePath = Path(selectedFile)
		copiedPath = self.dataFolder / sourcePath.name

		if sourcePath.resolve() != copiedPath.resolve():
			copy2(sourcePath, copiedPath)

			print(f"CSV copied from: {sourcePath}")
			print(f"CSV copied to: {copiedPath}")
		else:
			print("CSV is already inside the data folder.")

		self.csvPath = copiedPath

		try:
			self.data = pd.read_csv(self.csvPath)
		except Exception as error:
			print(f"CSV could not be loaded: {error}")
			return False

		requiredColumns = {
			"time_s",
			"value"
		}

		missingColumns = (
			requiredColumns -
			set(self.data.columns)
		)

		if missingColumns:
			print(
				"CSV is missing required columns: "
				f"{missingColumns}"
			)

			return False

		print(f"Working CSV loaded: {self.csvPath}")
		print()

		return True

	def askQuestions(self):
		self.graphChk = (
			input(
				"Would you like to see the graph? "
			).strip().lower() == "yes"
		)

		self.minChk = (
			input(
				"Would you like to see the minimum value? "
			).strip().lower() == "yes"
		)

		self.maxChk = (
			input(
				"Would you like to see the maximum value? "
			).strip().lower() == "yes"
		)

		self.meanChk = (
			input(
				"Would you like to see the mean value? "
			).strip().lower() == "yes"
		)

		print()

	def createWaveform(self):
		self.figure, axes = plt.subplots()

		axes.plot(
			self.data["time_s"],
			self.data["value"]
		)

		axes.set_title("ElectroStat Waveform")
		axes.set_xlabel("Time (s)")
		axes.set_ylabel("Voltage")
		axes.grid()

		csvName = self.csvPath.stem

		waveformOutput = (
			self.waveformFolder /
			f"{csvName}_waveform.png"
		)

		self.figure.savefig(
			waveformOutput,
			dpi=300,
			bbox_inches="tight"
		)

		print(f"Waveform saved to: {waveformOutput}")
		print()

	def printStatistics(self):
		if self.minChk:
			print(
				f"Minimum Value is: "
				f"{self.data['value'].min()}"
			)

		if self.maxChk:
			print(
				f"Maximum Value is: "
				f"{self.data['value'].max()}"
			)

		if self.meanChk:
			print(
				f"Mean Value is: "
				f"{self.data['value'].mean()}"
			)

	def showGraph(self):
		if self.graphChk:
			plt.show()
		else:
			plt.close(self.figure)

	def run(self):
		if not self.selectWorkingDirectory():
			return

		if not self.selectCSV():
			return

		self.askQuestions()
		self.createWaveform()
		self.printStatistics()
		self.showGraph()


def main():
	root = Tk()
	root.withdraw()

	electroStat = ElectroStat()

	try:
		electroStat.run()
	finally:
		root.destroy()


if __name__ == "__main__":
	main()
