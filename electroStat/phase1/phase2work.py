from tkinter import filedialog as fd
from pathlib import Path


def setupFolders():
    selectedDirectory = fd.askdirectory(
        title="Select ElectroStat output directory"
    )

    if selectedDirectory == "":
        print("Folder setup cancelled.")
        return

    outputDirectory = Path(selectedDirectory)

    waveformFolder = outputDirectory / "waveform"
    fftFolder = outputDirectory / "fft"

    waveformFolder.mkdir(exist_ok=True)
    fftFolder.mkdir(exist_ok=True)

    print(f"Waveform folder created at: {waveformFolder}")
    print(f"FFT folder created at: {fftFolder}")


def main():
    setupFolders()


if __name__ == "__main__":
    main()
