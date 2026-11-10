### Bumper Origins

@torbjornaxelsson created Bumper originally in 2017 and the project reached its original goal and remained in a stable, but stale state with the last commit in Dec 2017.  

Since the original release of Bumper newer bots have been released that use different protocols, and in early 2019 it was decided that @bmartin5692 would take over development moving forward.  This fork was detached and all future development of bumper will take place here.  

#### This fork

Development of [bmartin5692/bumper](https://github.com/bmartin5692/bumper) stopped in June 2021. The code depended on libraries that are no longer maintained and stopped working on newer Python versions.

[tunlezah/bumper](https://github.com/tunlezah/bumper), which these docs describe, forked it in 2026 and ported it to current Python, current libraries and a new Docker image, with a test harness that checks the port against recordings of the 2021 code. See [Modernisation](modernisation/CHANGES.md) for the details.

#### Archive

The original bumper code base has been branched off as [v0.1.0](https://github.com/bmartin5692/bumper/tree/v0.1.0) and will remain in the original state.  This branch *may* work for older models (M81 Pro, N79S, etc.), but the master branch should be tried first as it contains many changes and fixes over the original with active development moving forward.
