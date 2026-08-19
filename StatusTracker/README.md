### Current State of Repository:

- All functinalities are working as intended, atleast as per the basic tests.
- Test cases are not exhaustive. Boundary conditions and ambiguous scenarios are not tested.
- test_get_task() is not functioning as intended and has been commented out.
- delete_task() deletes task from session then commits to db.
- HTTP_404_NOT_FOUND added in get_task() for when a task is deleted or missing and cannot be found.
- Repository requires an exhaustive suite of tests.
