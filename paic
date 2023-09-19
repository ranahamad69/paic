"use strict";
//problem 1
var cel = 37;
var far = 212;
console.log("conterting celcious to farenheit:\n");
var f = (cel * 9) / 5 + 32;
var c = (far * 5) / 9 - 32;
console.log("temp in celcious=", cel);
console.log("cel to far= ", f);
console.log("temp in farenheit=", far);
console.log("far to cel= ", c);
//problem 2
var days = 234;
var rd = days % 7;
var w = (days - rd) / 7;
console.log("entered num of days", days);
console.log("entered days =\n", w, " weeks\t", rd, " days");
//problem 3
var days = 234;
var rd = days % 7;
var w = (days - rd) / 7;
console.log("entered num of days", days);
console.log("entered days =\n", w, " weeks\t", rd, " days");
//problem 4
var p1 = 110;
var p2 = 50;
console.log("price of product 1 before discount:\t", p1, "\nprice of product 2 before discount:\t", p2);
if (p1 >= 100 || p2 >= 100) {
    var dis = p1 * 0.1;
    p1 = p1 - dis;
}
if (p1 <= 100 || p2 <= 100) {
    var dis2 = p2 * 0.05;
    p2 = p2 - dis2;
}
console.log("\nprice of product 1 after discount:\t", p1);
console.log("\nprice of product 2 after discount:\t", p2);
//problem 5
var age1 = 7;
var age2 = 17;
var age3 = 29;
if (age3 > 20) {
    console.log("adult");
}
else if (age2 >= 13 && age2 <= 19) {
    console.log("teenager");
}
else if (age1 == 0 && age1 <= 12) {
    console.log("child");
}
//problem 6
var temp = 17;
if (temp < 27) {
    console.log("You should wear some warm clothes..\n");
}
else
    console.log("Its' gettinging warmer outiside....Warm clothes might not be a good option");
//problem 7
var num = 120;
if (num % 3 == 0 && num % 5 == 0) {
    console.log(num, " is divisible by 3 and 5");
}
else if (num % 3 == 0) {
    console.log(num, " is divisible by 3");
}
else if (num % 5 == 0) {
    console.log(num, " is divisible by 5");
}
// problem 8
var year = 2016;
if (year % 100 != 0 && year % 4 == 0) {
    console.log(year, " is a leap year");
}
// problem 9
var day = 1;
if (day == 1) {
    console.log("monday");
}
else if (day == 2) {
    console.log("tuesday");
}
else if (day == 2) {
    console.log("wednesday");
}
else if (day == 4) {
    console.log("thursday");
}
else if (day == 5) {
    console.log("friday");
}
else if (day == 6) {
    console.log("saturday");
}
else if (day == 7) {
    console.log("sunday");
}
else {
    console.log("invalid input");
}
//problem 10
var units = -17;
var priceOfunit = 40;
var calculated = (units * priceOfunit);
if (units >= 0 && units <= 100) {
    // formula to add tax
    var billCalculation = calculated + (10 / 100) * calculated;
    console.log(`Total units Consumed: ${units} and total bill with 10% tax:${billCalculation}`);
}
else if (units > 100 && units <= 200) {
    // formula to add tax
    var billCalculation = calculated + (15 / 100) * calculated;
    console.log(`Total units consumed: ${units} and total bill with 15% tax: ${billCalculation}`);
}
else if (units > 200 && units <= 500) {
    var billCalculation = calculated + (15 / 100) * calculated;
    console.log(`Total units consumed ${units} and total bill with 25% tax: ${billCalculation}`);
}
else {
    var billCalculation = calculated + (35 / 100) * calculated;
    console.log(`Total units consumed ${units} and total bill with 35% tax: ${billCalculation}`);
}
