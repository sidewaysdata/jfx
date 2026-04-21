This is the sidewaysdata fork of OpenJFX. We carry custom patches (e.g. the
scroll-fix on `bug-8328167-scroll-to-first-scroll`) and publish each `master`
commit to repsy as `org.openjfx:javafx-*:27.0.0-sd.<short-sha>` for the timer
desktop app to consume.

## Release / publish workflow

After advancing `master` (e.g. cherry-picking, merging a fix branch, rebasing
onto upstream):

1. Commit on `master`.
2. `python3 publish.py --platform linux` (script computes
   `27.0.0-sd.<git-short-sha>` and pushes the artifacts to repsy).
3. Bump `/home/winrid/dev/sidewaysdata/timer/build.gradle:89`
   `ext.jfxVersion` to the new sha.
4. From `timer/`: `./gradlew --refresh-dependencies clean jlink jpackage`
   then `timeout 5 build/jpackage/SidewaysData/bin/SidewaysData` — confirm
   `JavaFX Application Thread` reaches RUNNABLE and no exceptions.

Mac and Windows classifiers must be published from their respective hosts
(OpenJFX cannot cross-compile the native libs). `publish.py` warns after
each publish about which platform classifiers are still missing on repsy.

## Build prerequisites

- JDK 25+ (matches `build.properties`'s `jfx.build.jdk.version.min` and
  `jfx.jdk.target.version`). On this dev box: `JAVA_HOME=~/.sdkman/candidates/java/25.0.2-open`.
- Linux media-native build deps:
  `apt install libglib2.0-dev libasound2-dev libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libgtk-3-dev libpango1.0-dev`.
- Repsy credentials in `~/.m2/settings.xml` (id=`repsy`) or
  `repsyUsername`/`repsyPassword` Gradle props or `REPSY_USERNAME`/`REPSY_PASSWORD`
  env vars.

## Remotes

- `origin` → `git@github.com:sidewaysdata/jfx.git` (the publishable fork)
- `winrid` → `git@github.com:winrid/jfx.git` (personal upstream-PR fork)
- `upstream` → `https://github.com/openjdk/jfx.git`

## Don't touch

- `build.properties` version fields are upstream-managed; we override the
  published version via `-PMAVEN_VERSION=...` from `publish.py`, never by
  editing those fields.
- `gradlew` mode bit must stay 0755 (we fixed it locally because upstream
  ships it 0644 which breaks fresh clones).
