do shell script "open -a \"Spotify\""
delay 5

set resumeVolume to 45
set currentTrack to ""

on appIsRunning(appName)
	tell application "System Events" to (name of processes) contains appName
end appIsRunning

repeat while appIsRunning("Spotify")
	tell application "Spotify"
		if player state is playing then
			set currentTrack to current track
			
			if get sound volume > 0 then
				set resumeVolume to sound volume
			end if
			
			if currentTrack's name is "Advertisement" or currentTrack's artist is "Learn More" or currentTrack's artist is "Listen Now" or currentTrack's artist is "" then
				set sound volume to 0
			else if get sound volume = 0 then
				set sound volume to resumeVolume
			end if
		else
			set sound volume to resumeVolume
		end if
	end tell
	delay 0.5
end repeat
