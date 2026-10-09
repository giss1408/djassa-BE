Feature: The customer controls their number
  Fidelia only ties purchases to a phone number with the customer's consent
  (Law 2013-450, docs/Reglementation/ARTCI.md), and withdrawing it erases
  the points.

  Background:
    Given the demo shop is signed in to Fidelia Pro

  Scenario: Withdrawing consent erases the points
    Given the customer "07 12 34 56 78" agrees at the counter to collect points
    And the shop records 2 cash sales of 5000 F for that customer
    And the customer signs in to the Fidelia app with "07 12 34 56 78"
    When the customer withdraws their consent in the app
    Then the app says the points for 10000 F at the shop were erased
    And the app shows no points
    And the shop must ask the customer again before the next sale earns points
