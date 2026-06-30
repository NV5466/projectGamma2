machine_Name = "Black_hole"


voltage = 0
current = 0

voltage = input("please input voltage: ")
current = input("please input current: ")


power = float(voltage) * float(current)



print(f"Machine is: {machine_Name}") 
print(f"System of variables is:")
print(f"Voltage={voltage} Volts")
print(f"Current={current} Amps")
print(f"power is={power} Watts")



