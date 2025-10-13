#!/bin/bash

# Download MKV files from Google Drive leftovers folder to /volumes/CuSSD3
# One at a time with progress monitoring

DEST_DIR="/volumes/CuSSD3"
SOURCE="drive:leftovers"

# List of MKV files to download
files=(
    "217m_t1.mkv"
    "214m_t1.mkv" 
    "Copy of OFP20 760 M Het 040223.mkv"
    "218_t2.mkv"
    "217_t2.mkv"
    "217_t3.mkv"
    "218_t3.mkv"
    "215_t3.mkv"
    "214_t3.mkv"
    "214_t2.mkv"
    "976f.mkv"
    "OFP20_777_KO_F.mkv"
    "OFP20_779_KO_F.mkv"
    "OFP20_776_KO_F.mkv"
    "OFP20_799_Wt_M.mkv"
    "OFP20_798_Wt_M.mkv"
    "OFP20_790_Wt_F.mkv"
    "OFP20_788_Wt_F.mkv"
    "OFP20_789_Het_F.mkv"
    "OFP20_759_Het_M.mkv"
)

echo "Starting download of MKV files to $DEST_DIR"
echo "==========================================="
echo "Total files to download: ${#files[@]}"
echo ""

# Track success/failure
successful_downloads=()
failed_downloads=()

for file in "${files[@]}"; do
    echo ""
    echo "Downloading: $file"
    echo "Size: $(rclone size "$SOURCE/$file" --json 2>/dev/null | jq -r '.bytes // 0' | numfmt --to=iec-i --suffix=B 2>/dev/null || echo "Unknown")"
    echo "Starting at: $(date)"
    echo "Progress:"

    # Download with progress and continue on next file even if this fails
    rclone copy "$SOURCE/$file" "$DEST_DIR" \
        --progress \
        --stats=2s \
        --transfers=1 \
        --checkers=1 \
        --bwlimit=0

    if [ $? -eq 0 ]; then
        echo "✓ Successfully downloaded: $file"
        echo "Completed at: $(date)"
        successful_downloads+=("$file")
    else
        echo "✗ Failed to download: $file"
        echo "Continuing with next file..."
        failed_downloads+=("$file")
    fi

    echo "----------------------------------------"
done

echo ""
echo "Download Summary:"
echo "================"
echo "✓ Successful downloads (${#successful_downloads[@]}):"
for file in "${successful_downloads[@]}"; do
    echo "  - $file"
done

if [ ${#failed_downloads[@]} -gt 0 ]; then
    echo ""
    echo "✗ Failed downloads (${#failed_downloads[@]}):"
    for file in "${failed_downloads[@]}"; do
        echo "  - $file"
    done
fi

echo ""
echo "Script completed! Check the summary above for any failed downloads."
