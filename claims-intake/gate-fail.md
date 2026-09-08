Testing Gate RCA:

1. I created a PR with my current changes.
2. I then made sure that my checks were passing on github before simulating a pipeline failure.
3. Then I added a typo in one of the tests/.
4. mypy, and pytest failed locally.
5. Upon pushing, the the pipeline checks failed but it still ALLOWED me to merge the PR.
6. On further research, I found out that we need to set up a rule to protect the main, and make sure the tests are passing before they can be merged into main.
