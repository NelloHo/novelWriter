#! /bin/bash

# Use RAM disk if possible
if [ -d /dev/shm ]; then
    TEMP_BASE=/dev/shm
else
    TEMP_BASE=/tmp
fi

BUILD_DIR=$(mktemp -d "$TEMP_BASE/novelWriter-build-XXXXXX")
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SRC_DIR="$SCRIPT_DIR/../.."
RLS_DIR="$SRC_DIR/dist_macos"

echo "Script Dir: $SCRIPT_DIR"

cleanup () {
    if [ -d "$BUILD_DIR" ]; then
        rm -rf "$BUILD_DIR"
    fi
}
trap cleanup EXIT

echo "Building in: $BUILD_DIR"

OLD_CWD="$(pwd)"
VERSION="$(awk '/^__version__/{print substr($NF,2,length($NF)-2)}' $SRC_DIR/novelwriter/__init__.py)"

pushd "$SRC_DIR" || exit 1

# --- Prepare Files ----------------------------------------------------------------------------- #

echo "Generating Info.plist"
python3 setup.py gen-plist
if [ -f $SRC_DIR/setup/macos/Info.plist ]; then
    echo "Found: setup/macos/Info.plist"
else
    echo "Missing: setup/macos/Info.plist"
    exit 1
fi

# Check that other assets are present
echo "Checking assets"
if [ -f $SRC_DIR/novelwriter/assets/sample.zip ]; then
    echo "Found: novelwriter/assets/sample.zip"
else
    echo "Missing: novelwriter/assets/sample.zip"
    exit 1
fi
if [ -f $SRC_DIR/novelwriter/assets/manual.pdf ]; then
    echo "Found: novelwriter/assets/manual.pdf"
else
    echo "Missing: novelwriter/assets/manual.pdf"
    exit 1
fi
if [ -f $SRC_DIR/novelwriter/assets/i18n/nw_en_US.qm ]; then
    echo "Found: novelwriter/assets/i18n/nw_en_US.qm"
else
    echo "Missing: novelwriter/assets/i18n/nw_en_US.qm"
    exit 1
fi

echo "Content of current dir:"
ls -lah .

popd || exit 1
pushd "$BUILD_DIR"/ || exit 1

# --- Create Miniconda Env ---------------------------------------------------------------------- #

# install Miniconda, a self-contained Python distribution
echo "Downloading Miniconda ..."
curl -LO https://repo.continuum.io/miniconda/Miniconda3-latest-MacOSX-x86_64.sh
bash Miniconda3-latest-MacOSX-x86_64.sh -b -p ~/miniconda -f
rm Miniconda3-latest-MacOSX-x86_64.sh 
export PATH="$HOME/miniconda/bin:$PATH"

echo "Creating conda env ..."
# create conda env
conda create -n novelWriter -c conda-forge python=3.10 --yes
source activate novelWriter

echo "installing dictionaries ..."
conda install -c conda-forge enchant hunspell-en --yes

# Install dependencies
echo "installing python dependencies ..."
pip install -r "$SRC_DIR/requirements.txt"

# Leave conda env
conda deactivate

# --- Build App --------------------------------------------------------------------------------- #

echo "Building app bundle ..."
# create .app Framework
mkdir -p novelWriter.app/Contents/
mkdir novelWriter.app/Contents/MacOS novelWriter.app/Contents/Resources novelWriter.app/Contents/Resources/novelWriter
cp $SRC_DIR/setup/macos/Info.plist novelWriter.app/Contents/Info.plist

echo "Copying miniconda env to bundle ..."
cp -R ~/miniconda/envs/novelWriter/* novelWriter.app/Contents/Resources/

echo "Copying novelWriter to bundle ..."
FILES_COPY=(
    "CHANGELOG.md" "MANIFEST.in" "CREDITS.md" "LICENSE.md"
    "CONTRIBUTING.md" "CODE_OF_CONDUCT.md" "novelwriter"
    "novelWriter.py"
)

for file in "${FILES_COPY[@]}"; do
    echo "Copying $SRC_DIR/$file ..."
    cp -R $SRC_DIR/$file novelWriter.app/Contents/Resources/novelWriter/
done

cp $SRC_DIR/setup/macos/novelwriter.icns novelWriter.app/Contents/Resources/

# Create entry script
echo "Creating entry script ..."
cat > novelWriter.app/Contents/MacOS/novelWriter <<\EOF
#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
$DIR/../Resources/bin/python -sE $DIR/../Resources/novelWriter/novelWriter.py $@
EOF

# Make it executable
chmod a+x novelWriter.app/Contents/MacOS/novelWriter

# Do codesigning
# echo "Signing bundle ..."
# sudo codesign --sign - --deep --force --entitlements "$SCRIPT_DIR/../macos/App.entitlements" --options runtime "novelWriter.app/Contents/MacOS/novelWriter"

# Remove bloat
pushd novelWriter.app/Contents/Resources || exit 1

# --- Cleanup ----------------------------------------------------------------------------------- #

echo "Cleaning unused files from bundle ..."
# cleanup commands HERE
find . -type d -iname '__pycache__' -print0 | xargs -0 rm -r

rm -rf pkgs
rm -rf cmake
rm -rf share/{gtk-,}doc

# Remove the files from the 3.1 symlink
rm -rf lib/python3.1

# remove web engine
rm lib/python3.*/site-packages/PyQt5/QtWebEngine* || true
rm -r lib/python3.*/site-packages/PyQt5/Qt/translations/qtwebengine* || true
rm lib/python3.*/site-packages/PyQt5/Qt/resources/qtwebengine* || true
rm -r lib/python3.*/site-packages/PyQt5/Qt/qml/QtWebEngine* || true
rm -r lib/python3.*/site-packages/PyQt5/Qt/plugins/webview/libqtwebview* || true
rm lib/python3.*/site-packages/PyQt5/Qt/libexec/QtWebEngineProcess* || true
rm lib/python3.*/site-packages/PyQt5/Qt/lib/libQt5WebEngine* || true

popd || exit 1
popd || exit 1

# --- Create App Bundle-------------------------------------------------------------------------- #

echo "Packageing App ..."
mkdir -p $RLS_DIR

pushd $BUILD_DIR || exit 1
zip -qr novelWriter.app.zip  novelWriter.app
popd || exit 1

mv -v $BUILD_DIR/novelWriter.app.zip $RLS_DIR/novelWriter-"${VERSION}"-macos.app.zip

# --- Create DMG -------------------------------------------------------------------------------- #

# Generate .dmg
echo "Packageing DMG ..."
brew install create-dmg

# "--skip-jenkins" is a temporary workaround for https://github.com/create-dmg/create-dmg/issues/72
create-dmg --volname "novelWriter $VERSION" --volicon $SRC_DIR/setup/macos/novelwriter.icns \
    --window-pos 200 120 --window-size 800 400 --icon-size 100 \
    --icon novelWriter.app 200 190 --hide-extension novelWriter.app \
    --app-drop-link 600 185 $RLS_DIR/novelWriter-"${VERSION}"-macos.dmg "$BUILD_DIR"/
