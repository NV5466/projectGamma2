from tkinter import filedialog as fd
from tkinter import Tk
from pathlib import Path
from itertools import combinations


def askChannelCount():
	while True:
		try:
			channelCount = int(input("How many channels? "))

			if channelCount < 1:
				print("Channel count must be at least 1.")
				continue

			return channelCount

		except ValueError:
			print("Enter a whole number.")


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
	waveformPairFolder = waveformFolder / "pairwise"
	fftPairFolder = fftFolder / "pairwise"

	dataFolder.mkdir(parents=True, exist_ok=True)
	waveformFolder.mkdir(parents=True, exist_ok=True)
	fftFolder.mkdir(parents=True, exist_ok=True)
	scriptsFolder.mkdir(parents=True, exist_ok=True)
	waveformPairFolder.mkdir(parents=True, exist_ok=True)
	fftPairFolder.mkdir(parents=True, exist_ok=True)

	channelCount = askChannelCount()
	channelNames = [
		f"CH{number}"
		for number in range(1, channelCount + 1)
	]

	for channelName in channelNames:
		(waveformFolder / channelName).mkdir(exist_ok=True)
		(fftFolder / channelName).mkdir(exist_ok=True)

	for channelA, channelB in combinations(channelNames, 2):
		pairName = f"{channelA}_{channelB}"
		(waveformPairFolder / pairName).mkdir(exist_ok=True)
		(fftPairFolder / pairName).mkdir(exist_ok=True)

	print()
	print(f"ElectroStat workspace created at: {rootFolder}")
	print(f"Channels created: {channelCount}")
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
