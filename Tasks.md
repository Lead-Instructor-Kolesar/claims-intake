### Objective:

- Day 2: Implement the two modules that sit at the edges of the service: models.py, which decides what a valid request is, and repository.py, which decides what a recorded claim is. Then write the unit tests that pin both.

### Tasks:

1. Understand what policy_client.py is actually trying to accomplish (apart from the obvious).
2. Start with tdd.py in tests, write a bunch of tests first then dive into implementation.
3. Build Policy model from class PolicyRecord.

### Completed:

1. Two tests now work which are basically checking if the notification request is valid and if the description field is optional.
2. The next test that passes checks if empty policy number is rejected, this was achieved by simply checking the the policy_number field has a minimum length of 1.
3. Added Literal[claim types] in the field of claim_type, to validate if claims type is valid.
4. Added Field to estimated_amount to validate 2 tests - ensuring its not 0 and limited to two decimal points.
5. After implementing all the changes in the class NotificationRequest, it checks if the policy is being read, it does not check if the claim is allowed. Its a glorified checker for V-1.




### Commands:

testing: uv run --with pytest-cov pytest tests/tdd.py --cov

