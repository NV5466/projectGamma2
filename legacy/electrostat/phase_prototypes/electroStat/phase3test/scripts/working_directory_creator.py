from tkinter import filedialog as fd
from tkinter import Tk
from pathlib import Path


def createWorkingDirectory():
	selectedDirectory = fd.askdirectory(
		title="Select ElectroStat working directory"
	)

	if selectedDirectory == "":
		print("Working directory selection cancelled.")
		return False

	rootFolder = Path(selectedDirectory)

	dataFolder = rootFolder / "data"
	waveformFolder = rootFolder / "waveform"
	fftFolder = rootFolder / "fft"
	scriptsFolder = rootFolder / "scripts"

	dataFolder.mkdir(exist_ok=True)
	waveformFolder.mkdir(exist_ok=True)
	fftFolder.mkdir(exist_ok=True)
	scriptsFolder.mkdir(exist_ok=True)

	print()
	print(f"Working directory created at: {rootFolder}")
	print(f"Data folder: {dataFolder}")
	print(f"Waveform folder: {waveformFolder}")
	print(f"FFT folder: {fftFolder}")
	print(f"Scripts folder: {scriptsFolder}")
	print()

	return True


def main():
	root = Tk()
	root.withdraw()

	try:
		createWorkingDirectory()
	finally:
		root.destroy()


if __name__ == "__main__":
	main()
