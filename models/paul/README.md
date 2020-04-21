# Models


# Ver01
- model is consistent and will normally run multiple laps
- lap times are 18-19secs
- Set "AI_THROTTLE_MULT = 1.0"
- Model file: paul-tub20-ver01.h5
- Data zip file: tub_20_20-04-20.zip

# Ver01 slide 200ms
- using naisy's tool to slide image and control data offset to 200ms
- Testing
	- Local sim: set "SIM_ARTIFICIAL_LATENCY = 200" in my config
	- Remote testing
		1. Ping remote sim server to get ping times
		2. Subtract ping time from 200ms (eg 200-100 for 100ms ping time)
		3. set "SIM_ARTIFICIAL_LATENCY = <step 2 value>"
- Model file: paul-tub20-ver01-slide200.h5
- Data zip file: tub_20_20-04-20_slide200.zip

# Ver02

- This model will go a little faster than Ver01
- lap times are ~18 secs
- Found that model is more robust if you set "AI_THROTTLE_MULT = 0.95"
- Model file: paul-tub21-ver02.h5
- Data zip file: tub_21_20-04-20.zip


![Model sim screenshot](https://github.com/Ottawa-Autonomous-Vehicle-Group/Simulator_racer/blob/master/models/paul/ver02/Screenshot%20from%202020-04-21%2000-49-10.png)


# Ver02 slide 200ms
- Found that model is more robust if you set "AI_THROTTLE_MULT = 0.95"
- using naisy's tool to slide image and control data offset to 200ms
- Testing
	- Local sim: set "SIM_ARTIFICIAL_LATENCY = 200" in my config
	- Remote testing
		1. Ping remote sim server to get ping times
		2. Subtract ping time from 200ms (eg 200-100 for 100ms ping time)
		3. set "SIM_ARTIFICIAL_LATENCY = <step 2 value>"

- Model file: paul-tub21-ver02-slide200.h5
- Data zip file: tub_21_20-04-20_slide200.zip


# Ver03 line racer
- This is a simple line follower based on Tawn's racer.py standalone client script
- It uses the cross-track error (cte) and a simple PID (Kp and KD only) to keep the car in the right lane
- It is limited in speed because it reacts too slowly when there is a quick change in the track such as a hairpin turn
- Fastest lap with current PID is ~28 secs
- Possible improvements would be a look-ahead if we had the layout and our position on the track
- Python racing client script: line_racer_v01.py
- Usage: python line_racer_v01.py --model=<model filename> --host=<sim host>=--name=<name of racer>
