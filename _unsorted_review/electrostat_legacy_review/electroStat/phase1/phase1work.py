# Information about the fake waveform contained in the CSV:
# - Channel: CH1
# - Signal: 1 kHz sine wave
# - Sampling rate: 20 kHz
# - Capture duration: 0.1 seconds
# - Amplitude: 2 V
# - DC offset: 0.25 V
# - Small amount of random noise added


# Import the file dialog system from tkinter.
#
# tkinter is Python's built-in GUI library.
# filedialog contains functions that open native Windows file-selection windows.
#
# "as fd" gives filedialog the shorter alias "fd".
# This means we can write:
#
#     fd.askopenfilename()
#
# instead of:
#
#     filedialog.askopenfilename()
from tkinter import filedialog as fd


import matplotlib.pyplot as plt

# Import the pandas library.
#
# pandas is used for reading and manipulating table-shaped data.
# "as pd" gives pandas the conventional alias "pd".
import pandas as pd


# Open a Windows file-selection dialog.
#
# askopenfilename() pauses the Python program until the user either:
# 1. selects a file, or
# 2. closes/cancels the file browser.
#
# The function returns the complete path of the selected file as a string.
#
# Example returned value:
# C:/Users/dmaca/Documents/JTAStuff/projectGamma/electroStat/data.csv
file_path1 = fd.askopenfilename(

    # Text displayed at the top of the file-selection window.
    title="Select waveform CSV",

    # Limit the visible selectable files to CSV files.
    #
    # This is a list of file type filters.
    # Each filter contains:
    # ("Description shown to user", "filename pattern")
    #
    # "*.csv" means:
    # any filename ending in .csv
    filetypes=[("CSV files", "*.csv")]
)


# Read the selected CSV file.
#
# file_path1 contains the address of the selected file.
#
# pd.read_csv() does the following:
# 1. Opens the file.
# 2. Reads the text.
# 3. Detects the comma-separated columns.
# 4. Uses the first row as column names.
# 5. Converts the data into a pandas DataFrame.
#
# A DataFrame is pandas' table object.
#
# In this case, the DataFrame contains columns:
# index, time_s, channel, value
d1 = pd.read_csv(file_path1)


# Display the first five rows of the DataFrame.
#
# .head() returns the first five rows by default.
# It is mainly used to verify that the file loaded correctly
# and that the columns contain what we expected.


#real shit 
#print (f"Maximum: {d1['value'].max()}")
#print (f"Minimum: {d1['value'].min()}")
#print (f"Average: {d1['value'].mean()}")


#So, ok, we need to do this for fft. WE CHOOSE A CUT OFF HEIGHT 
#FOR GENERAL HARMONIC SANITY, WE FIND MAXIMUM VALUE, match the 
#VALUE TO THE INDEX ITS IN, WE DELETE THAT INDEX, then we do 
#that for all other points until none are hitting the cut off, 
#then we match those removed indexes to their frequencies, 
#and if they are within some percentage of each other then 
#clearly they are apart of the same frequency spike.

#We take the whole fft and take the derivative (hold on I know 
#just wait) then what we do is every 2 samples ill call a line 
#of work. We take each line of work and compare their slope. We 
#walk the fft derivative, and check the max value of slope along 
#the fft. WE also compare the largest magnitude slope indicies 
#WITH the index of each maximum fft value. And max a cluster that way

w1 = plt.plot(d1["time_s"],d1["value"])
plt.title("Electrostat waveform")
plt.xlabel("Time(s)")
plt.ylabel("Voltage")
plt.grid()


gridChk = 0

class CommandLineTest:
    def __init__(self, data):
        self.data = data

        self.graphChk = False
        self.minChk = False
        self.maxChk = False
        self.meanChk = False

    def ques(self):
        self.graphChk = input(
            "Hello, would you like to see the graph? "
        ).lower() == "yes"

        self.minChk = input(
            "Would you like to see the min value? "
        ).lower() == "yes"

        self.maxChk = input(
            "Would you like to see the max value? "
        ).lower() == "yes"

        self.meanChk = input(
            "Would you like to see the mean value? "
        ).lower() == "yes"

    def maxStuff(self, chk: bool):
        if chk:
            print(f"Maximum Value is: {self.data['value'].max()}")

    def minStuff(self, chk: bool):
        if chk:
            print(f"Minimum Value is: {self.data['value'].min()}")

    def meanStuff(self, chk: bool):
        if chk:
            print(f"Mean Value is: {self.data['value'].mean()}")

    def graphStuff(self, chk: bool):
        if chk:
            plt.show()

    def runLines(self):
        self.ques()

        self.minStuff(self.minChk)
        self.maxStuff(self.maxChk)
        self.meanStuff(self.meanChk)
        self.graphStuff(self.graphChk)



def main():
	command_line = CommandLineTest(d1)
	command_line.runLines()
	
if __name__ == "__main__":
	main()
