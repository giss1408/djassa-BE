Feature: Loyalty, ça compte
  A customer earns points at the shops they already use, by their phone
  number, with or without the customer app, and the shop turns those points
  into rewards.

  Background:
    Given the demo shop is signed in to Fidelia Pro

  Scenario: A cash customer earns points and gets a reward at the counter
    Given the customer "07 12 34 56 78" agrees at the counter to collect points
    When the shop records 8 cash sales of 5000 F for that customer
    Then the customer has the points for 40000 F at the shop
    When the shop hands over its cheapest reward to the customer
    Then the customer gets a 6-character voucher code
    And the reward's cost is taken off the customer's points

  Scenario: Points earned at the counter show up in the customer app
    Given the customer "07 12 34 56 78" agrees at the counter to collect points
    And the shop records 2 cash sales of 5000 F for that customer
    When the customer signs in to the Fidelia app with "07 12 34 56 78"
    Then the app shows the points for 10000 F at the shop

  Scenario: A sale sent twice from the offline queue earns points once
    Given the customer "07 12 34 56 78" agrees at the counter to collect points
    When the phone sends the same sale of 5000 F twice after a lost connection
    Then the shop has 1 sale for that customer
    And the customer has the points for 5000 F at the shop

  Scenario: A number without consent earns nothing
    When the shop records a cash sale of 5000 F for "07 12 34 56 78" without asking for consent
    Then the sale is refused so the shop can ask the customer
    And the customer has no points at the shop
