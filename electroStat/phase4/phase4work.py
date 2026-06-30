from tkinter import filedialog as fd
from tkinter import Tk
from pathlib import Path
from shutil import copy2
from itertools import combinations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import (
	coherence,
	correlate,
	correlation_lags,
	csd,
	find_peaks,
	welch
)


class ElectroStat:
	def __init__(self):
		# Workspace paths
		self.rootFolder = None
		self.dataFolder = None
		self.waveformFolder = None
		self.fftFolder = None
		self.scriptsFolder = None

		# Channel and pair folders
		self.channelCount = 0
		self.channelNames = []
		self.waveformChannelFolders = {}
		self.fftChannelFolders = {}
		self.waveformPairFolders = {}
		self.fftPairFolders = {}

		# Imported waveform data
		self.channels = {}

		# Analysis results
		self.channelStatistics = []
		self.harmonicRows = []
		self.pairStatistics = []

		# Display choice
		self.showPlots = False
		self.openFigures = []

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

		self.dataFolder.mkdir(parents=True, exist_ok=True)
		self.waveformFolder.mkdir(parents=True, exist_ok=True)
		self.fftFolder.mkdir(parents=True, exist_ok=True)
		self.scriptsFolder.mkdir(parents=True, exist_ok=True)

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
			"from itertools import combinations",
			"",
			"",
			"def askChannelCount():",
			"\twhile True:",
			"\t\ttry:",
			"\t\t\tchannelCount = int(input(\"How many channels? \"))",
			"",
			"\t\t\tif channelCount < 1:",
			"\t\t\t\tprint(\"Channel count must be at least 1.\")",
			"\t\t\t\tcontinue",
			"",
			"\t\t\treturn channelCount",
			"",
			"\t\texcept ValueError:",
			"\t\t\tprint(\"Enter a whole number.\")",
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
			"\twaveformPairFolder = waveformFolder / \"pairwise\"",
			"\tfftPairFolder = fftFolder / \"pairwise\"",
			"",
			"\tdataFolder.mkdir(parents=True, exist_ok=True)",
			"\twaveformFolder.mkdir(parents=True, exist_ok=True)",
			"\tfftFolder.mkdir(parents=True, exist_ok=True)",
			"\tscriptsFolder.mkdir(parents=True, exist_ok=True)",
			"\twaveformPairFolder.mkdir(parents=True, exist_ok=True)",
			"\tfftPairFolder.mkdir(parents=True, exist_ok=True)",
			"",
			"\tchannelCount = askChannelCount()",
			"\tchannelNames = [",
			"\t\tf\"CH{number}\"",
			"\t\tfor number in range(1, channelCount + 1)",
			"\t]",
			"",
			"\tfor channelName in channelNames:",
			"\t\t(waveformFolder / channelName).mkdir(exist_ok=True)",
			"\t\t(fftFolder / channelName).mkdir(exist_ok=True)",
			"",
			"\tfor channelA, channelB in combinations(channelNames, 2):",
			"\t\tpairName = f\"{channelA}_{channelB}\"",
			"\t\t(waveformPairFolder / pairName).mkdir(exist_ok=True)",
			"\t\t(fftPairFolder / pairName).mkdir(exist_ok=True)",
			"",
			"\tprint()",
			"\tprint(f\"ElectroStat workspace created at: {rootFolder}\")",
			"\tprint(f\"Channels created: {channelCount}\")",
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

	def askChannelCount(self):
		while True:
			try:
				self.channelCount = int(
					input("How many channels? ")
				)

				if self.channelCount < 1:
					print("Channel count must be at least 1.")
					continue

				self.channelNames = [
					f"CH{number}"
					for number in range(
						1,
						self.channelCount + 1
					)
				]

				return True

			except ValueError:
				print("Enter a whole number.")

	def createChannelFolders(self):
		waveformPairRoot = (
			self.waveformFolder /
			"pairwise"
		)

		fftPairRoot = (
			self.fftFolder /
			"pairwise"
		)

		waveformPairRoot.mkdir(exist_ok=True)
		fftPairRoot.mkdir(exist_ok=True)

		for channelName in self.channelNames:
			waveformChannelFolder = (
				self.waveformFolder /
				channelName
			)

			fftChannelFolder = (
				self.fftFolder /
				channelName
			)

			waveformChannelFolder.mkdir(exist_ok=True)
			fftChannelFolder.mkdir(exist_ok=True)

			self.waveformChannelFolders[channelName] = (
				waveformChannelFolder
			)

			self.fftChannelFolders[channelName] = (
				fftChannelFolder
			)

		for channelA, channelB in combinations(
			self.channelNames,
			2
		):
			pairName = f"{channelA}_{channelB}"

			waveformPairFolder = (
				waveformPairRoot /
				pairName
			)

			fftPairFolder = (
				fftPairRoot /
				pairName
			)

			waveformPairFolder.mkdir(exist_ok=True)
			fftPairFolder.mkdir(exist_ok=True)

			self.waveformPairFolders[pairName] = (
				waveformPairFolder
			)

			self.fftPairFolders[pairName] = (
				fftPairFolder
			)

		print()
		print(
			f"Created channel folders for "
			f"{self.channelCount} channel(s)."
		)
		print()

	def selectChannelCSVs(self):
		for channelName in self.channelNames:
			if not self.selectCSV(channelName):
				return False

		return True

	def selectCSV(self, channelName):
		selectedFile = fd.askopenfilename(
			title=f"Select waveform CSV for {channelName}",
			filetypes=[("CSV files", "*.csv")]
		)

		if selectedFile == "":
			print(f"{channelName} CSV selection cancelled.")
			return False

		sourcePath = Path(selectedFile)

		if (
			sourcePath.parent.resolve() ==
			self.dataFolder.resolve()
		):
			copiedPath = sourcePath
			print(
				f"{channelName} CSV is already inside "
				f"the data folder."
			)
		else:
			copiedPath = (
				self.dataFolder /
				f"{channelName}_{sourcePath.name}"
			)

			copy2(sourcePath, copiedPath)

			print(f"{channelName} CSV copied from: {sourcePath}")
			print(f"{channelName} CSV copied to: {copiedPath}")

		try:
			data = pd.read_csv(copiedPath)
		except Exception as error:
			print(f"{channelName} CSV could not be loaded: {error}")
			return False

		requiredColumns = {
			"time_s",
			"value"
		}

		missingColumns = (
			requiredColumns -
			set(data.columns)
		)

		if missingColumns:
			print(
				f"{channelName} CSV is missing required columns: "
				f"{missingColumns}"
			)

			return False

		cleanData = (
			data[["time_s", "value"]]
			.apply(pd.to_numeric, errors="coerce")
			.dropna()
			.sort_values("time_s")
			.drop_duplicates(subset="time_s")
		)

		if len(cleanData) < 8:
			print(
				f"{channelName} needs at least 8 valid samples."
			)
			return False

		timeValues = cleanData["time_s"].to_numpy(
			dtype=float
		)

		signalValues = cleanData["value"].to_numpy(
			dtype=float
		)

		timeSteps = np.diff(timeValues)

		if np.any(timeSteps <= 0):
			print(
				f"{channelName} contains invalid time ordering."
			)
			return False

		sampleInterval = float(
			np.median(timeSteps)
		)

		samplingFrequency = 1.0 / sampleInterval

		self.channels[channelName] = {
			"csvPath": copiedPath,
			"data": cleanData,
			"time": timeValues,
			"values": signalValues,
			"sampleInterval": sampleInterval,
			"samplingFrequency": samplingFrequency
		}

		print(
			f"{channelName} loaded with "
			f"{len(signalValues)} samples."
		)
		print()

		return True

	def askDisplayChoice(self):
		self.showPlots = (
			input(
				"Would you like to display all plots after analysis? "
			).strip().lower() == "yes"
		)

		print()

	def keepOrCloseFigure(self, figure):
		if self.showPlots:
			self.openFigures.append(figure)
		else:
			plt.close(figure)

	def createWaveformPlot(self, channelName):
		channel = self.channels[channelName]

		figure, axes = plt.subplots()

		axes.plot(
			channel["time"],
			channel["values"]
		)

		axes.set_title(
			f"ElectroStat Waveform - {channelName}"
		)

		axes.set_xlabel("Time (s)")
		axes.set_ylabel("Voltage")
		axes.grid()

		outputPath = (
			self.waveformChannelFolders[channelName] /
			f"{channelName}_waveform.png"
		)

		figure.savefig(
			outputPath,
			dpi=300,
			bbox_inches="tight"
		)

		self.keepOrCloseFigure(figure)

		print(
			f"{channelName} waveform saved to: "
			f"{outputPath}"
		)

	def calculateSpectrum(self, channelName):
		channel = self.channels[channelName]

		signalValues = channel["values"]
		sampleInterval = channel["sampleInterval"]
		sampleCount = len(signalValues)

		centeredSignal = (
			signalValues -
			np.mean(signalValues)
		)

		window = np.hanning(sampleCount)
		coherentGain = np.sum(window) / sampleCount

		fftValues = np.fft.rfft(
			centeredSignal *
			window
		)

		frequencies = np.fft.rfftfreq(
			sampleCount,
			d=sampleInterval
		)

		magnitudes = (
			2.0 *
			np.abs(fftValues) /
			(sampleCount * coherentGain)
		)

		if len(magnitudes) > 0:
			magnitudes[0] = (
				np.abs(fftValues[0]) /
				(sampleCount * coherentGain)
			)

		return frequencies, magnitudes

	def detectHarmonics(
		self,
		channelName,
		frequencies,
		magnitudes
	):
		if len(frequencies) < 3:
			return None, []

		positiveMagnitudes = magnitudes[1:]

		if (
			len(positiveMagnitudes) == 0 or
			np.max(positiveMagnitudes) <= 0
		):
			return None, []

		maximumMagnitude = float(
			np.max(positiveMagnitudes)
		)

		noiseFloor = float(
			np.median(positiveMagnitudes)
		)

		prominenceThreshold = max(
			maximumMagnitude * 0.02,
			noiseFloor * 6.0
		)

		peakIndexes, peakProperties = find_peaks(
			magnitudes[1:],
			prominence=prominenceThreshold,
			distance=2
		)

		peakIndexes = peakIndexes + 1

		if len(peakIndexes) == 0:
			dominantIndex = (
				int(np.argmax(positiveMagnitudes)) +
				1
			)

			peakIndexes = np.array(
				[dominantIndex]
			)

		peakMagnitudes = magnitudes[peakIndexes]
		strongestPeakMagnitude = float(
			np.max(peakMagnitudes)
		)

		fundamentalCandidates = peakIndexes[
			peakMagnitudes >=
			strongestPeakMagnitude * 0.10
		]

		if len(fundamentalCandidates) == 0:
			fundamentalIndex = int(
				peakIndexes[
					np.argmax(peakMagnitudes)
				]
			)
		else:
			fundamentalIndex = int(
				fundamentalCandidates[
					np.argmin(
						frequencies[
							fundamentalCandidates
						]
					)
				]
			)

		fundamentalFrequency = float(
			frequencies[fundamentalIndex]
		)

		if fundamentalFrequency <= 0:
			return None, []

		frequencyResolution = float(
			frequencies[1] -
			frequencies[0]
		)

		nyquistFrequency = float(
			frequencies[-1]
		)

		maximumOrder = int(
			nyquistFrequency /
			fundamentalFrequency
		)

		harmonicRows = []

		for harmonicOrder in range(
			1,
			maximumOrder + 1
		):
			targetFrequency = (
				harmonicOrder *
				fundamentalFrequency
			)

			tolerance = max(
				2.0 * frequencyResolution,
				0.02 * targetFrequency
			)

			peakErrors = np.abs(
				frequencies[peakIndexes] -
				targetFrequency
			)

			closestPeakPosition = int(
				np.argmin(peakErrors)
			)

			closestPeakIndex = int(
				peakIndexes[
					closestPeakPosition
				]
			)

			frequencyError = float(
				peakErrors[
					closestPeakPosition
				]
			)

			if frequencyError > tolerance:
				continue

			detectedFrequency = float(
				frequencies[closestPeakIndex]
			)

			detectedMagnitude = float(
				magnitudes[closestPeakIndex]
			)

			relativeMagnitude = (
				detectedMagnitude /
				float(magnitudes[fundamentalIndex])
			)

			harmonicRow = {
				"channel": channelName,
				"harmonic_order": harmonicOrder,
				"target_frequency_hz": targetFrequency,
				"detected_frequency_hz": detectedFrequency,
				"frequency_error_hz": frequencyError,
				"magnitude": detectedMagnitude,
				"relative_to_fundamental": relativeMagnitude
			}

			harmonicRows.append(harmonicRow)

		return fundamentalFrequency, harmonicRows

	def createFFTAnalysis(self, channelName):
		frequencies, magnitudes = (
			self.calculateSpectrum(channelName)
		)

		fundamentalFrequency, harmonicRows = (
			self.detectHarmonics(
				channelName,
				frequencies,
				magnitudes
			)
		)

		figure, axes = plt.subplots()

		axes.plot(
			frequencies,
			magnitudes
		)

		if harmonicRows:
			harmonicFrequencies = [
				row["detected_frequency_hz"]
				for row in harmonicRows
			]

			harmonicMagnitudes = [
				row["magnitude"]
				for row in harmonicRows
			]

			axes.scatter(
				harmonicFrequencies,
				harmonicMagnitudes
			)

		axes.set_title(
			f"ElectroStat FFT - {channelName}"
		)

		axes.set_xlabel("Frequency (Hz)")
		axes.set_ylabel("Magnitude")
		axes.grid()

		outputPath = (
			self.fftChannelFolders[channelName] /
			f"{channelName}_fft.png"
		)

		figure.savefig(
			outputPath,
			dpi=300,
			bbox_inches="tight"
		)

		self.keepOrCloseFigure(figure)

		harmonicPath = (
			self.fftChannelFolders[channelName] /
			f"{channelName}_harmonic_peaks.csv"
		)

		pd.DataFrame(harmonicRows).to_csv(
			harmonicPath,
			index=False
		)

		self.harmonicRows.extend(harmonicRows)

		positiveMagnitudes = magnitudes[1:]

		if len(positiveMagnitudes) > 0:
			dominantIndex = (
				int(np.argmax(positiveMagnitudes)) +
				1
			)

			dominantFrequency = float(
				frequencies[dominantIndex]
			)
		else:
			dominantFrequency = float("nan")

		print(
			f"{channelName} FFT saved to: "
			f"{outputPath}"
		)

		print(
			f"{channelName} harmonic table saved to: "
			f"{harmonicPath}"
		)

		return dominantFrequency, fundamentalFrequency

	def createPSD(self, channelName):
		channel = self.channels[channelName]

		signalValues = channel["values"]
		samplingFrequency = channel["samplingFrequency"]

		nperseg = min(
			1024,
			len(signalValues)
		)

		frequencies, powerDensity = welch(
			signalValues,
			fs=samplingFrequency,
			window="hann",
			nperseg=nperseg,
			noverlap=nperseg // 2,
			detrend="constant",
			scaling="density"
		)

		figure, axes = plt.subplots()

		axes.semilogy(
			frequencies,
			powerDensity
		)

		axes.set_title(
			f"ElectroStat PSD - {channelName}"
		)

		axes.set_xlabel("Frequency (Hz)")
		axes.set_ylabel("PSD (V²/Hz)")
		axes.grid()

		outputPath = (
			self.fftChannelFolders[channelName] /
			f"{channelName}_psd.png"
		)

		figure.savefig(
			outputPath,
			dpi=300,
			bbox_inches="tight"
		)

		self.keepOrCloseFigure(figure)

		psdDataPath = (
			self.fftChannelFolders[channelName] /
			f"{channelName}_psd.csv"
		)

		pd.DataFrame({
			"frequency_hz": frequencies,
			"psd_v2_per_hz": powerDensity
		}).to_csv(
			psdDataPath,
			index=False
		)

		print(
			f"{channelName} PSD saved to: "
			f"{outputPath}"
		)

	def createAutocorrelation(self, channelName):
		channel = self.channels[channelName]

		signalValues = channel["values"]
		samplingFrequency = channel["samplingFrequency"]

		centeredSignal = (
			signalValues -
			np.mean(signalValues)
		)

		autoCorrelation = correlate(
			centeredSignal,
			centeredSignal,
			mode="full",
			method="fft"
		)

		lagSamples = correlation_lags(
			len(centeredSignal),
			len(centeredSignal),
			mode="full"
		)

		lagSeconds = (
			lagSamples /
			samplingFrequency
		)

		zeroLagValue = float(
			np.max(np.abs(autoCorrelation))
		)

		if zeroLagValue > 0:
			autoCorrelation = (
				autoCorrelation /
				zeroLagValue
			)

		figure, axes = plt.subplots()

		axes.plot(
			lagSeconds,
			autoCorrelation
		)

		axes.set_title(
			f"ElectroStat Autocorrelation - {channelName}"
		)

		axes.set_xlabel("Lag (s)")
		axes.set_ylabel("Normalized correlation")
		axes.grid()

		outputPath = (
			self.waveformChannelFolders[channelName] /
			f"{channelName}_autocorrelation.png"
		)

		figure.savefig(
			outputPath,
			dpi=300,
			bbox_inches="tight"
		)

		self.keepOrCloseFigure(figure)

		print(
			f"{channelName} autocorrelation saved to: "
			f"{outputPath}"
		)

	def calculateChannelStatistics(
		self,
		channelName,
		dominantFrequency,
		fundamentalFrequency
	):
		channel = self.channels[channelName]

		signalValues = channel["values"]
		timeValues = channel["time"]

		statisticsRow = {
			"channel": channelName,
			"sample_count": len(signalValues),
			"duration_s": float(
				timeValues[-1] -
				timeValues[0]
			),
			"sampling_frequency_hz": float(
				channel["samplingFrequency"]
			),
			"minimum": float(
				np.min(signalValues)
			),
			"maximum": float(
				np.max(signalValues)
			),
			"mean": float(
				np.mean(signalValues)
			),
			"peak_to_peak": float(
				np.ptp(signalValues)
			),
			"rms": float(
				np.sqrt(
					np.mean(
						np.square(signalValues)
					)
				)
			),
			"dominant_frequency_hz": dominantFrequency,
			"fundamental_frequency_hz": (
				fundamentalFrequency
				if fundamentalFrequency is not None
				else float("nan")
			)
		}

		self.channelStatistics.append(
			statisticsRow
		)

		print()
		print(f"{channelName} statistics")
		print(
			f"Frequency: "
			f"{statisticsRow['fundamental_frequency_hz']} Hz"
		)
		print(
			f"Peak-to-peak: "
			f"{statisticsRow['peak_to_peak']}"
		)
		print(
			f"RMS: "
			f"{statisticsRow['rms']}"
		)
		print()

	def analyzeChannel(self, channelName):
		self.createWaveformPlot(channelName)

		dominantFrequency, fundamentalFrequency = (
			self.createFFTAnalysis(channelName)
		)

		self.createPSD(channelName)
		self.createAutocorrelation(channelName)

		self.calculateChannelStatistics(
			channelName,
			dominantFrequency,
			fundamentalFrequency
		)

	def alignChannelPair(
		self,
		channelAName,
		channelBName
	):
		channelA = self.channels[channelAName]
		channelB = self.channels[channelBName]

		startTime = max(
			channelA["time"][0],
			channelB["time"][0]
		)

		endTime = min(
			channelA["time"][-1],
			channelB["time"][-1]
		)

		if endTime <= startTime:
			raise ValueError(
				f"{channelAName} and {channelBName} "
				f"do not overlap in time."
			)

		commonInterval = max(
			channelA["sampleInterval"],
			channelB["sampleInterval"]
		)

		sampleCount = int(
			np.floor(
				(endTime - startTime) /
				commonInterval
			)
		) + 1

		if sampleCount < 8:
			raise ValueError(
				f"{channelAName} and {channelBName} "
				f"have too little overlapping data."
			)

		commonTime = (
			startTime +
			np.arange(sampleCount) *
			commonInterval
		)

		signalA = np.interp(
			commonTime,
			channelA["time"],
			channelA["values"]
		)

		signalB = np.interp(
			commonTime,
			channelB["time"],
			channelB["values"]
		)

		samplingFrequency = (
			1.0 /
			commonInterval
		)

		return (
			commonTime,
			signalA,
			signalB,
			samplingFrequency
		)

	def createCrossCorrelation(
		self,
		pairName,
		channelAName,
		channelBName,
		signalA,
		signalB,
		samplingFrequency
	):
		centeredA = signalA - np.mean(signalA)
		centeredB = signalB - np.mean(signalB)

		crossCorrelation = correlate(
			centeredA,
			centeredB,
			mode="full",
			method="fft"
		)

		normalization = np.sqrt(
			np.sum(np.square(centeredA)) *
			np.sum(np.square(centeredB))
		)

		if normalization > 0:
			crossCorrelation = (
				crossCorrelation /
				normalization
			)

		lagSamples = correlation_lags(
			len(centeredA),
			len(centeredB),
			mode="full"
		)

		lagSeconds = (
			lagSamples /
			samplingFrequency
		)

		bestIndex = int(
			np.argmax(
				np.abs(crossCorrelation)
			)
		)

		bestLag = float(
			lagSeconds[bestIndex]
		)

		bestCorrelation = float(
			crossCorrelation[bestIndex]
		)

		figure, axes = plt.subplots()

		axes.plot(
			lagSeconds,
			crossCorrelation
		)

		axes.set_title(
			f"Cross-correlation - "
			f"{channelAName} vs {channelBName}"
		)

		axes.set_xlabel("Lag (s)")
		axes.set_ylabel("Normalized correlation")
		axes.grid()

		outputPath = (
			self.waveformPairFolders[pairName] /
			f"{pairName}_cross_correlation.png"
		)

		figure.savefig(
			outputPath,
			dpi=300,
			bbox_inches="tight"
		)

		self.keepOrCloseFigure(figure)

		print(
			f"{pairName} cross-correlation saved to: "
			f"{outputPath}"
		)

		return bestLag, bestCorrelation

	def createCSDAndCoherence(
		self,
		pairName,
		channelAName,
		channelBName,
		signalA,
		signalB,
		samplingFrequency
	):
		nperseg = min(
			1024,
			len(signalA),
			len(signalB)
		)

		csdFrequencies, crossPower = csd(
			signalA,
			signalB,
			fs=samplingFrequency,
			window="hann",
			nperseg=nperseg,
			noverlap=nperseg // 2,
			detrend="constant",
			scaling="density"
		)

		coherenceFrequencies, coherenceValues = coherence(
			signalA,
			signalB,
			fs=samplingFrequency,
			window="hann",
			nperseg=nperseg,
			noverlap=nperseg // 2,
			detrend="constant"
		)

		csdFigure, csdAxes = plt.subplots()

		csdAxes.semilogy(
			csdFrequencies,
			np.abs(crossPower)
		)

		csdAxes.set_title(
			f"CSD - {channelAName} vs {channelBName}"
		)

		csdAxes.set_xlabel("Frequency (Hz)")
		csdAxes.set_ylabel("|CSD| (V²/Hz)")
		csdAxes.grid()

		csdOutputPath = (
			self.fftPairFolders[pairName] /
			f"{pairName}_csd.png"
		)

		csdFigure.savefig(
			csdOutputPath,
			dpi=300,
			bbox_inches="tight"
		)

		self.keepOrCloseFigure(csdFigure)

		coherenceFigure, coherenceAxes = plt.subplots()

		coherenceAxes.plot(
			coherenceFrequencies,
			coherenceValues
		)

		coherenceAxes.set_title(
			f"Coherence - "
			f"{channelAName} vs {channelBName}"
		)

		coherenceAxes.set_xlabel("Frequency (Hz)")
		coherenceAxes.set_ylabel("Magnitude-squared coherence")
		coherenceAxes.set_ylim(0, 1.05)
		coherenceAxes.grid()

		coherenceOutputPath = (
			self.fftPairFolders[pairName] /
			f"{pairName}_coherence.png"
		)

		coherenceFigure.savefig(
			coherenceOutputPath,
			dpi=300,
			bbox_inches="tight"
		)

		self.keepOrCloseFigure(coherenceFigure)

		pairSpectralPath = (
			self.fftPairFolders[pairName] /
			f"{pairName}_spectral_data.csv"
		)

		pd.DataFrame({
			"frequency_hz": coherenceFrequencies,
			"coherence": coherenceValues,
			"csd_magnitude": np.abs(crossPower),
			"csd_phase_radians": np.angle(crossPower)
		}).to_csv(
			pairSpectralPath,
			index=False
		)

		peakCoherenceIndex = int(
			np.argmax(coherenceValues)
		)

		peakCoherence = float(
			coherenceValues[
				peakCoherenceIndex
			]
		)

		peakCoherenceFrequency = float(
			coherenceFrequencies[
				peakCoherenceIndex
			]
		)

		print(
			f"{pairName} CSD saved to: "
			f"{csdOutputPath}"
		)

		print(
			f"{pairName} coherence saved to: "
			f"{coherenceOutputPath}"
		)

		return (
			peakCoherence,
			peakCoherenceFrequency
		)

	def analyzePair(
		self,
		channelAName,
		channelBName
	):
		pairName = (
			f"{channelAName}_"
			f"{channelBName}"
		)

		try:
			(
				commonTime,
				signalA,
				signalB,
				samplingFrequency
			) = self.alignChannelPair(
				channelAName,
				channelBName
			)

		except ValueError as error:
			print(error)
			return

		bestLag, bestCorrelation = (
			self.createCrossCorrelation(
				pairName,
				channelAName,
				channelBName,
				signalA,
				signalB,
				samplingFrequency
			)
		)

		(
			peakCoherence,
			peakCoherenceFrequency
		) = self.createCSDAndCoherence(
			pairName,
			channelAName,
			channelBName,
			signalA,
			signalB,
			samplingFrequency
		)

		self.pairStatistics.append({
			"pair": pairName,
			"channel_a": channelAName,
			"channel_b": channelBName,
			"aligned_sample_count": len(commonTime),
			"aligned_sampling_frequency_hz": samplingFrequency,
			"best_cross_correlation_lag_s": bestLag,
			"best_cross_correlation_value": bestCorrelation,
			"peak_coherence": peakCoherence,
			"peak_coherence_frequency_hz": peakCoherenceFrequency
		})

	def saveSummaryTables(self):
		channelStatisticsPath = (
			self.dataFolder /
			"channel_statistics.csv"
		)

		pd.DataFrame(
			self.channelStatistics
		).to_csv(
			channelStatisticsPath,
			index=False
		)

		harmonicSummaryPath = (
			self.dataFolder /
			"harmonic_peaks.csv"
		)

		pd.DataFrame(
			self.harmonicRows
		).to_csv(
			harmonicSummaryPath,
			index=False
		)

		if self.pairStatistics:
			pairStatisticsPath = (
				self.dataFolder /
				"pairwise_statistics.csv"
			)

			pd.DataFrame(
				self.pairStatistics
			).to_csv(
				pairStatisticsPath,
				index=False
			)

			print(
				f"Pairwise statistics saved to: "
				f"{pairStatisticsPath}"
			)

		print(
			f"Channel statistics saved to: "
			f"{channelStatisticsPath}"
		)

		print(
			f"Harmonic summary saved to: "
			f"{harmonicSummaryPath}"
		)

	def run(self):
		if not self.selectWorkingDirectory():
			return

		if not self.askChannelCount():
			return

		self.createChannelFolders()

		if not self.selectChannelCSVs():
			return

		self.askDisplayChoice()

		for channelName in self.channelNames:
			self.analyzeChannel(channelName)

		for channelA, channelB in combinations(
			self.channelNames,
			2
		):
			self.analyzePair(
				channelA,
				channelB
			)

		self.saveSummaryTables()

		print()
		print("ElectroStat Phase 4 analysis complete.")
		print()

		if self.showPlots:
			plt.show()


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

