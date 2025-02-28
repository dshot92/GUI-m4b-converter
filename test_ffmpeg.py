import ffmpeg
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

# Test ffmpeg-python functionality
def test_ffmpeg():
    try:
        # Create a simple ffmpeg command
        input_file = "test_input.mp3"  # This doesn't need to exist for this test
        output_file = "test_output.m4a"
        
        # Create input stream
        input_stream = ffmpeg.input(input_file)
        
        # Create output with options
        output = (
            ffmpeg
            .output(
                input_stream,
                output_file,
                c='aac',
                b='128k',
                map='0:a'
            )
            .overwrite_output()
        )
        
        # Print the command that would be executed
        print("Command that would be executed:")
        print(output.compile())
        
        print("\nTest successful!")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    test_ffmpeg() 