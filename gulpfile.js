"use strict";


var gulp = require('gulp');
var gutil = require('gulp-util');
var uglify = require('gulp-uglify');
var concat = require('gulp-concat');
var rename = require('gulp-rename');
var shell = require('gulp-shell');
var exec = require('child_process').exec;
var execSync = require('child_process').execSync;
var fs = require('fs');
var path = require('path');
var del = require('del');
var _ = require('underscore');


// Script Inital Working Directory
var sondaor_rootdir = process.cwd();



// OHIF
var sonador_styles = './styles/';
var sonador_jslib = './sonador/jslib/';
var sonador_static = './sonador/static/';
var sonador_static_css = sonador_static+'css/';
var sonador_static_js = sonador_static+'js/';

var guru_jslib = './lib/guru/jslib/';
var guru_static = './lib/guru/static/';
var guru_static_css = guru_static+'css/';
var guru_static_js = guru_static+'js/';

var visionaire_jslib = './apps/visionaire/jslib/';
var visionaire_jslib_ohif = visionaire_jslib+'ohif/';
var visionaire_static = './apps/visionare/static/';
var visionaire_static_css = visionaire_static+'css/';
var visionaire_static_js = visionaire_static+'js/';


// Content
var content_jslib = './lib/content/jslib/';
var content_jslib_ace = content_jslib+'ace/';
var content_static = './lib/content/static/';
var content_static_js = content_static+'js/';
var content_static_css = content_static+'css/';


function jsBuildOHIF(done){
	console.log('Compile and copy OHIF: ', visionaire_jslib_ohif);

	var visionaire_jslib_ohif_node_deps = visionaire_jslib_ohif+'node_modules/';
	var ohif_deps, build_ohif;

	try {

		// Determine if necessary dependencies are installed
		ohif_deps = fs.lstatSync(visionaire_jslib_ohif_node_deps);
		build_ohif = true;

	} catch(err) {

		// Dependencies not yet installed, change to Foundation directory and install
		try {
			console.info('Dependencies for OHIF have not yet been installed. Install to: ',
				visionaire_jslib_ohif_node_deps);
			process.chdir(visionaire_jslib_ohif);
			execSync('yarn install')
			console.info('OHIF dependencies installed successfully');
			build_ohif = true;
			process.chdir(sondaor_rootdir);

		} catch(err) {

			// Indicate that an error occurred, stop build
			console.error('Error occurrered while trying to install node dependencies: ', err);
			process.chdir(sondaor_rootdir);
			return 1;

		}
	} finally {

		if (build_ohif) { 
			try {
				process.chdir(visionaire_jslib_ohif);

				// Execute Foundation build script
				console.info('Build OHIF with default options');
				execSync('yarn run build');
				console.info('Build of OHIF completed successfully');

				process.chdir(sondaor_rootdir);
			} catch(err){

				// Indicate that an error occurred, stop build
				console.error('Error while trying to build OHIF: ', err);
				process.chdir(sondaor_rootdir);
			}
		}
	}

	return gulp.src(visionaire_jslib_ohif+'platform/viewer/dist/**/*').pipe(gulp.dest(visionaire_static_js+'ohif/'));
}



function jsBuildAce(done) {
	console.log('Compile and minify ACE code editor: ', content_jslib_ace);
	var content_jslib_ace_node_deps = content_jslib_ace+'node_modules/';
	var ace_deps, build_ace;

	try {

		// Determine if necessary dependencies are installed
		ace_deps = fs.lstatSync(content_jslib_ace_node_deps);
		build_ace = true;

	} catch (err) {

		// Dependencies not yet installed, cahnge to jslib directory and install
		try {

			console.info('Dependencies for ACE JS have not yet been installed. Install to ',
				content_jslib_ace_node_deps);
			process.chdir(content_jslib_ace);
			execSync('npm install');
			console.info('ACE JS depdencies installed succesfully');
			build_ace = true;
			process.chdir(sondaor_rootdir);
		} catch (err) {

			// Indicate that an error occurred, stop build
			console.log('Error while trying to install node dependencies: ', err);
			process.chdir(sondaor_rootdir);
			done();
		}
	} finally {

		if (build_ace) {
			try {
				process.chdir(content_jslib_ace);

				// Execue ACE build script
				console.log('Build ACE JS with default options');
				execSync('node ./Makefile.dryice.js');
				console.info('Build of ACE JS completed succesfully');

				process.chdir(sondaor_rootdir);
			} catch (err) {

				// Indicate that an error occurred, stop build
				console.log('Error while trying to build ACE JS: ', err);
				process.chdir(sondaor_rootdir);
				done();
			}
		} else { done(); }
	}

	return gulp.src(content_jslib_ace+'build/src/**/*.js')
		.pipe(gulp.dest(content_static_js+'ace/'));
}


const js = gulp.series(jsBuildOHIF,);


exports.jsBuildOHIF = jsBuildOHIF;
exports.jsBuildAce = jsBuildAce;
exports.js = js;
